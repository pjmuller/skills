// bw-broker: the compiled core of bw-once's Touch ID path. Every security decision lives here, not in the
// editable Python front end: the request panel (personal phrase, agent's claim, checked facts), Touch ID,
// unsealing the master passwords, Bitwarden's signed CLI over a private socket, exact-host filtering, lock +
// verify, clipboard delivery. stdin: one request JSON; stdout: one result JSON (metadata only).
//
// Storage: one legacy Keychain item per broker build whose ACL trusts only that build (another or a modified binary
// gets a visible macOS prompt; an update hands it over with one Touch ID), holding the phrase and a bundle of master
// passwords sealed to a Secure Enclave key that only works after Touch ID (`.biometryCurrentSet`, enforced by the
// enclave).
import AppKit
import CryptoKit
import Darwin
import Foundation
import LocalAuthentication
import Security

// MARK: - Basics

struct Failure: Error { let message: String }

#if BW_BROKER_TEST
// Test build only (pytest compiles it with -D BW_BROKER_TEST): fake CLI, file store, fake enclave, hidden panel.
let testEnv = ProcessInfo.processInfo.environment
#endif

let bitwardenRequirement =
    "anchor apple generic and identifier \"bw\" and certificate leaf[subject.OU] = \"LTZ2PFU5D6\""
#if BW_BROKER_STAGING
let keychainService = "bw-once-staging"
#else
let keychainService = "bw-once"
#endif
let keychainAccount = "broker"
let clipboardSeconds = 30
let fillSeconds = 60  // `--to page`: one fetch by the approved host's page within this.
var stdoutWritten = false
#if BW_BROKER_TEST
let resultSeconds = 0.0
#else
let resultSeconds = 1.8  // Long enough to read "Copied … · vault locked".
#endif

func finish(_ result: [String: Any]) -> Never {
    if !stdoutWritten, let data = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]) {
        stdoutWritten = true
        FileHandle.standardOutput.write(data + Data("\n".utf8))
    }
    exit(result["ok"] as? Bool == true ? 0 : 1)
}

func fail(_ message: String) -> Never { finish(["ok": false, "error": message]) }

/// Answer the front end now and keep running (the agent's pick arrives later over a private socket).
func emit(_ result: [String: Any]) {
    guard !stdoutWritten, let data = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]) else { return }
    stdoutWritten = true
    FileHandle.standardOutput.write(data + Data("\n".utf8))
    let null = open("/dev/null", O_WRONLY)
    dup2(null, 1)  // EOF for the front end, which returns the candidates to the agent.
    close(null)
}

/// One deadline for the whole request, renewal panels included (each restarts its own 300 s watchdog): the
/// front end stops waiting at this + 30 s (bw_once.BROKER_SECONDS) and reports nothing released, so nothing is.
let answerSeconds: Double = {
    #if BW_BROKER_TEST
    return Double(ProcessInfo.processInfo.environment["BW_BROKER_TEST_ANSWER_SECONDS"] ?? "300")!
    #else
    return 300
    #endif
}()
let answerDeadline = Date().addingTimeInterval(answerSeconds)

let pickSeconds: Double = {
    #if BW_BROKER_TEST
    return Double(ProcessInfo.processInfo.environment["BW_BROKER_TEST_PICK_SECONDS"] ?? "60")!
    #else
    return 60
    #endif
}()

/// After a copy the same thread may re-copy that one login's username/password without a touch for this long
/// (Google asks for the password twice in one sign-in; a gcloud OAuth right after asks again).
let recopySeconds: Double = {
    #if BW_BROKER_TEST
    return Double(ProcessInfo.processInfo.environment["BW_BROKER_TEST_RECOPY_SECONDS"] ?? "900")!
    #else
    return 15 * 60
    #endif
}()

func socketPath(_ name: String) -> String {
    #if BW_BROKER_TEST
    let directory = ProcessInfo.processInfo.environment["BW_BROKER_TEST_SOCKDIR"]!
    #else
    let directory = (ProcessInfo.processInfo.environment["HOME"] ?? NSHomeDirectory()) + "/.cache/bw-once"
    #endif
    return directory + "/\(name).sock"
}

/// Private socket (0600): `pick-<random token>` (the agent names a login) or `recopy-<key>` (see `recopyKey`).
func privateSocket(_ name: String) throws -> (Int32, String) {
    let path = socketPath(name)
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)
    guard fd >= 0, path.utf8.count < MemoryLayout.size(ofValue: address.sun_path) else { throw Failure(message: "Cannot open \(name)") }
    withUnsafeMutableBytes(of: &address.sun_path) { raw in
        _ = path.withCString { strncpy(raw.baseAddress!.assumingMemoryBound(to: CChar.self), $0, raw.count - 1) }
    }
    let previous = umask(0o177)
    defer { umask(previous) }
    let bound = withUnsafePointer(to: &address) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) }
    }
    guard bound == 0, listen(fd, 4) == 0 else { close(fd); throw Failure(message: "Cannot open \(name)") }
    return (fd, path)
}

func readRequestLine(_ fd: Int32, until deadline: Date) -> [String: Any]? {
    // One absolute limit (≤5 s, never past the deadline): a client trickling bytes can't stretch a window.
    let end = min(deadline, Date().addingTimeInterval(5))
    var data = Data()
    var buffer = [UInt8](repeating: 0, count: 1024)
    while !data.contains(10), data.count < 4096 {
        let left = end.timeIntervalSinceNow
        guard left > 0 else { return nil }
        var timeout = timeval(tv_sec: Int(left), tv_usec: Int32((left - Double(Int(left))) * 1_000_000))
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
        let n = read(fd, &buffer, buffer.count)
        guard n > 0 else { break }
        data.append(contentsOf: buffer[0..<n])
    }
    return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
}

func reply(_ fd: Int32, _ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) {
        (data + Data("\n".utf8)).withUnsafeBytes { _ = write(fd, $0.baseAddress!, $0.count) }
    }
    close(fd)
}

let here: URL = {
    var size = UInt32(PATH_MAX)
    var buffer = [CChar](repeating: 0, count: Int(size))
    _ = _NSGetExecutablePath(&buffer, &size)
    return URL(fileURLWithPath: String(cString: buffer)).resolvingSymlinksInPath().deletingLastPathComponent()
}()

// MARK: - Request validation (repeats the front end's checks; the front end is not trusted)

struct Vault {
    let name: String
    let email: String
    let appdata: String?
}

struct Request {
    let op: String
    let vaults: [Vault]
    var host = "", field = "", username: String? = nil, id: String? = nil, to = "clipboard"
    var thread: String? = nil, why: String? = nil
}

func text(_ value: Any?, max: Int) -> String? {
    guard let value = value as? String, !value.isEmpty, value.count <= max,
          !value.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 || (0x80...0x9f).contains($0.value)
              || (0x202a...0x202e).contains($0.value) || (0x2066...0x2069).contains($0.value) }) else { return nil }
    return value
}

func exactHost(_ value: Any?) -> String? {
    guard let value = (value as? String)?.lowercased(), value.count <= 253,
          value.range(of: #"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"#,
                      options: .regularExpression) != nil else { return nil }
    return value
}

func parseRequest(_ data: Data) throws -> Request {
    guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let op = json["op"] as? String, ["list", "copy", "enroll", "status", "forget"].contains(op),
          let rawVaults = json["vaults"] as? [[String: Any]], !rawVaults.isEmpty, rawVaults.count <= 8 else {
        throw Failure(message: "Invalid broker request")
    }
    var vaults: [Vault] = []
    for raw in rawVaults {
        guard let name = raw["name"] as? String, name.range(of: #"^[a-z0-9-]{1,32}$"#, options: .regularExpression) != nil,
              let email = text(raw["email"], max: 254)?.lowercased(), email.contains("@") else {
            throw Failure(message: "Each Touch ID vault needs a name and an account email in vaults.json")
        }
        let appdata = raw["appdata"] as? String
        if let appdata, !appdata.hasPrefix("/") { throw Failure(message: "Vault appdata must be absolute") }
        vaults.append(Vault(name: name, email: email, appdata: appdata))
    }
    var request = Request(op: op, vaults: vaults)
    if op == "list" || op == "copy" {
        guard let host = exactHost(json["host"]) else { throw Failure(message: "Use an exact DNS host") }
        request.host = host
        request.thread = json["thread"] is NSNull ? nil : text(json["thread"], max: 120)
        request.why = json["why"] is NSNull ? nil : text(json["why"], max: 200)
        if (json["thread"] != nil && !(json["thread"] is NSNull) && request.thread == nil)
            || (json["why"] != nil && !(json["why"] is NSNull) && request.why == nil) {
            throw Failure(message: "--thread (≤120) and --why (≤200) must be plain text")
        }
        if let username = json["username"], !(username is NSNull) {
            guard let value = text(username, max: 254) else { throw Failure(message: "Invalid username") }
            request.username = value.lowercased()
        }
    }
    if op == "copy" {
        guard let field = json["field"] as? String, ["username", "password", "totp"].contains(field) else {
            throw Failure(message: "Unsupported credential field")
        }
        request.field = field
        if let to = json["to"], !(to is NSNull) {
            guard let value = to as? String, ["clipboard", "page"].contains(value) else { throw Failure(message: "--to clipboard|page") }
            request.to = value
        }
        if let id = json["id"], !(id is NSNull) {
            guard let value = (id as? String)?.lowercased(), UUID(uuidString: value) != nil else {
                throw Failure(message: "Use an exact item UUID")
            }
            request.id = value
        }
    }
    return request
}

// MARK: - Keychain (legacy file keychain, one item per broker build)
//
// macOS binds a legacy item to the code hash (cdhash) of the ad-hoc signed build that created it (ACL + partition
// list): that build reads and deletes it without a dialog; any other build, so every rebuilt broker, needs the Mac
// login password, and a one-off "Allow" (the dialog's default button) asks again on every request (2026-10-25). A
// build can't grant another one access (the partition list keeps only its creator) and a self-signed certificate
// gets no Team ID, so its partition is still the cdhash (both checked 2026-10-25). Hence one item per build
// (account "broker-<cdhash>"): after an update the previous build (bw-broker.prev, kept by the installer) shows the
// phrase and hands its item over after one Touch ID; the new build saves its own and deletes the old ones (deleting
// is bound to the creator's path, not its hash: checked 2026-10-25). macOS asks for the password only when no
// previous build can read an item silently (the first move to this scheme).

let ownAccount: String = {
    #if BW_BROKER_TEST
    let previous = CommandLine.arguments[0].hasSuffix(".prev")
    return "broker-" + (testEnv[previous ? "BW_BROKER_TEST_PREV_BUILD" : "BW_BROKER_TEST_BUILD"] ?? "test")
    #endif
    var me: SecCode?
    SecCodeCopySelf([], &me)
    return "broker-" + (me.flatMap { cdhash(unsafeBitCast($0, to: SecStaticCode.self)) } ?? "unsigned")
}()

func cdhash(_ code: SecStaticCode) -> String? {
    var info: CFDictionary?
    guard SecCodeCopySigningInformation(code, [], &info) == errSecSuccess,
          let unique = (info as? [String: Any])?[kSecCodeInfoUnique as String] as? Data else { return nil }
    return unique.map { String(format: "%02x", $0) }.joined()
}

func keychainQuery(_ account: String? = ownAccount) -> [String: Any] {
    var query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: keychainService,
                                kSecUseDataProtectionKeychain as String: false]
    query[kSecAttrAccount as String] = account
    return query
}

#if BW_BROKER_TEST
func testStore(_ account: String) -> String {
    account == "broker-test" ? testEnv["BW_BROKER_TEST_STORE"]! : testEnv["BW_BROKER_TEST_STORE"]! + ".item-" + account
}
#endif

/// Every build's item, newest first: account and enrolled vault names (comment attribute). No dialog, no secret.
func keychainItems() -> [(account: String, vaults: [String])] {
    #if BW_BROKER_TEST
    let store = URL(fileURLWithPath: testEnv["BW_BROKER_TEST_STORE"]!)
    let names = (try? FileManager.default.contentsOfDirectory(atPath: store.deletingLastPathComponent().path)) ?? []
    return names.sorted().compactMap { name in
        let prefix = store.lastPathComponent + ".item-"
        guard let account = name == store.lastPathComponent ? "broker-test"
                : name.hasPrefix(prefix) ? String(name.dropFirst(prefix.count)) : nil else { return nil }
        let item = (try? JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: testStore(account)))))
        return (account, (((item as? [String: Any])?["vaults"] as? [[String: String]]) ?? []).compactMap { $0["name"] })
    }
    #endif
    var query = keychainQuery(nil)
    query[kSecReturnAttributes as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitAll
    var result: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let rows = result as? [[String: Any]] else {
        return []
    }
    func modified(_ row: [String: Any]) -> Date { row[kSecAttrModificationDate as String] as? Date ?? .distantPast }
    return rows.sorted { modified($0) > modified($1) }.map {
        (($0[kSecAttrAccount as String] as? String) ?? "",
         (($0[kSecAttrComment as String] as? String) ?? "").split(separator: ",").map(String.init))
    }
}

/// May show the macOS dialog when `account` is another build's item.
func keychainLoad(_ account: String = ownAccount) throws -> [String: Any]? {
    #if BW_BROKER_TEST
    guard let data = FileManager.default.contents(atPath: testStore(account)) else { return nil }
    if account != ownAccount { FileHandle.standardError.write(Data("keychain dialog: \(account)\n".utf8)) }
    return try JSONSerialization.jsonObject(with: data) as? [String: Any]
    #endif
    var query = keychainQuery(account)
    query[kSecReturnData as String] = true
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound { return nil }
    guard status == errSecSuccess, let data = result as? Data,
          let item = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        throw Failure(message: status == errSecUserCanceled || status == errSecAuthFailed
            ? "Keychain access denied" : "Cannot read the bw-once Keychain item (\(status))")
    }
    return item
}

enum SilentRead { case loaded([String: Any]?), needsPrompt }

/// The item without any macOS dialog, or `.needsPrompt`. `kSecUseAuthenticationUIFail` is ignored by legacy ACLs
/// (still shows the dialog, checked 2026-10-24); the old per-process switch is out of the headers but still exported.
func keychainLoadSilently(_ account: String = ownAccount) -> SilentRead {
    #if BW_BROKER_TEST
    if account != ownAccount { return .needsPrompt }
    return (try? .loaded(keychainLoad(account))) ?? .needsPrompt
    #endif
    // Can't probe: explain anyway rather than risk an unexplained prompt. Not `try? load()`: it flattens "none".
    return withoutKeychainDialogs { (try? .loaded(keychainLoad(account))) ?? .needsPrompt } ?? .needsPrompt
}

func withoutKeychainDialogs<T>(_ body: () -> T) -> T? {
    typealias Toggle = @convention(c) (DarwinBoolean) -> OSStatus
    guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "SecKeychainSetUserInteractionAllowed") else {
        return nil
    }
    let allowUI = unsafeBitCast(symbol, to: Toggle.self)
    _ = allowUI(false)
    defer { _ = allowUI(true) }
    return body()
}

/// Runs `body` on the main queue with this build's item, taking it over from the previous build after an update.
func withKeychainItem(_ body: @escaping (Result<[String: Any]?, Error>) -> Void) {
    switch keychainLoadSilently() {
    case .loaded(let item?):
        try? FileManager.default.removeItem(at: previousBuild)  // E.g. a reinstall of the same build.
        return body(.success(item))
    case .needsPrompt: return body(Result { try keychainLoad() })  // Ours but unreadable: never a new phrase.
    case .loaded(nil): break
    }
    guard let stale = keychainItems().first(where: { $0.account != ownAccount }) else { return body(.success(nil)) }
    DispatchQueue.global().async {
        do {
            if let item = try takeOver() { return onMain { body(.success(item)) } }
        } catch { return onMain { body(.failure(error)) } }
        #if BW_BROKER_STAGING
        return onMain { body(.failure(Failure(message: "staging: macOS would ask"))) }
        #endif
        onMain { promptedTakeOver(stale.account, body) }
    }
}

let previousBuild = here.appendingPathComponent("bw-broker.prev")

/// Asks the previous build (`{"op":"handoff"}`) for its item: nil when there is none that can read it silently (or
/// it predates the hand-over); throws when the human cancelled its window.
func takeOver(check: Bool = false) throws -> [String: Any]? {
    guard FileManager.default.isExecutableFile(atPath: previousBuild.path) else { return nil }
    let child = Process()
    child.executableURL = previousBuild
    #if BW_BROKER_TEST
    child.environment = testEnv
    #else
    child.environment = ["PATH": "/usr/bin:/bin", "HOME": NSHomeDirectory()]
    #endif
    let input = Pipe(), output = Pipe()
    child.standardInput = input
    child.standardOutput = output
    try child.run()
    input.fileHandleForWriting.write(Data((check ? #"{"op":"handoff-check"}"# : #"{"op":"handoff"}"#).utf8))
    try? input.fileHandleForWriting.close()
    let answer = try? JSONSerialization.jsonObject(with: output.fileHandleForReading.readDataToEndOfFile()) as? [String: Any]
    guard answer?["ok"] as? Bool == true else {
        child.waitUntilExit()
        if answer?["declined"] as? Bool == true { throw Failure(message: "bw-once update not approved; nothing released") }
        return nil
    }
    if check { return [:] }
    child.waitUntilExit()
    guard let item = answer?["handoff"] as? [String: Any] else { return nil }
    try keychainSave(item)
    return item
}

/// No previous build could hand over: macOS asks once for the login password (Allow is enough: we save our own).
func promptedTakeOver(_ account: String, _ body: @escaping (Result<[String: Any]?, Error>) -> Void) {
    let built = (try? FileManager.default.attributesOfItem(atPath: here.appendingPathComponent("bw-broker").path))?[.modificationDate]
        as? Date
    let notice = Panel(title: "bw-once · macOS asks for Keychain access")
    notice.line("bw-once's broker was rebuilt" + (built.map { " on " + DateFormatter.localizedString(
        from: $0, dateStyle: .medium, timeStyle: .short) } ?? "") + " (a bw-once update). macOS now asks, up to "
        + "twice, for your Mac login password before it may open its saved item.")
    notice.line("Allow is enough: bw-once then keeps its own copy, and later updates need only Touch ID.", size: 13)
    notice.line("Not expecting a bw-once update? Choose Deny.", color: .systemOrange)
    notice.show()
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {  // Drawn before the system dialog covers it.
        let result = Result { () throws -> [String: Any]? in
            guard let item = try keychainLoad(account) else { return nil }
            try keychainSave(item)
            return item
        }
        notice.window.close()
        body(result)
    }
}

/// The old build's side (`{"op":"handoff"}` on stdin): only the installed bw-broker (running code checked) may ask;
/// one Touch ID in a window with the phrase releases this build's item to it.
func handOver(check: Bool) {
    guard case .loaded(let item?) = keychainLoadSilently() else { fail("Nothing to hand over") }
    let installed = here.appendingPathComponent("bw-broker")
    #if !BW_BROKER_TEST
    var parent: SecCode?
    var file: SecStaticCode?
    guard SecCodeCopyGuestWithAttributes(nil, [kSecGuestAttributePid: getppid()] as CFDictionary, [], &parent)
            == errSecSuccess, let parent, SecCodeCheckValidity(parent, [], nil) == errSecSuccess,
          SecStaticCodeCreateWithPath(installed as CFURL, [], &file) == errSecSuccess, let file,
          let running = cdhash(unsafeBitCast(parent, to: SecStaticCode.self)), running == cdhash(file) else {
        fail("Hand-over refused: the caller is not the installed bw-broker")
    }
    #endif
    if check { finish(["ok": true]) }
    let built = (try? FileManager.default.attributesOfItem(atPath: installed.path))?[.modificationDate] as? Date
    let panel = Panel(title: "bw-once · update")
    panel.line("Your bw-once phrase:", color: .secondaryLabelColor, size: 11)
    panel.line(item["phrase"] as? String ?? "?", size: 18, mono: true)
    panel.line("bw-once was updated" + (built.map { " (" + DateFormatter.localizedString(from: $0, dateStyle: .medium,
        timeStyle: .short) + ")" } ?? "") + ". Touch ID lets the new version use your saved Bitwarden passwords; no "
        + "Mac password needed. The request itself follows in its own window.")
    panel.line("Not expecting a bw-once update? Cancel.", color: .systemOrange)
    let context = LAContext()
    panel.onCancel = { context.invalidate(); finish(["ok": false, "declined": true]) }
    panel.button("Cancel") { panel.window.close() }
    DispatchQueue.main.asyncAfter(deadline: .now() + 300) { panel.window.close() }
    #if !BW_BROKER_STAGING
    panel.show()
    #endif
    panel.setStatus("Touch ID to approve…")
    approveWithTouch(context, reason: "let the updated bw-once use your saved passwords") { approved in
        onMain {
            guard approved else { return panel.window.close() }
            panel.onCancel = {}
            finish(["ok": true, "handoff": item])
        }
    }
}

func approveWithTouch(_ context: LAContext, reason: String, _ done: @escaping (Bool) -> Void) {
    #if BW_BROKER_TEST
    FileHandle.standardError.write(Data("touch: \(reason)\n".utf8))
    return done(testEnv["BW_BROKER_TEST_TOUCH"] != "cancel")
    #elseif BW_BROKER_STAGING
    return done(true)
    #endif
    context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: reason) { ok, _ in done(ok) }
}

/// Saves this build's item and drops older builds' (and the previous build itself): no longer needed.
func keychainSave(_ item: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: item)
    #if BW_BROKER_TEST
    try data.write(to: URL(fileURLWithPath: testStore(ownAccount)))
    keychainItems().filter { $0.account != ownAccount }.forEach { try? FileManager.default.removeItem(atPath: testStore($0.account)) }
    try? FileManager.default.removeItem(at: previousBuild)
    return
    #endif
    keychainDelete()
    var add = keychainQuery()
    add[kSecValueData as String] = data
    add[kSecAttrLabel as String] = "bw-once (Touch ID broker)"
    add[kSecAttrComment as String] = ((item["vaults"] as? [[String: String]]) ?? []).compactMap { $0["name"] }
        .joined(separator: ",")
    let status = SecItemAdd(add as CFDictionary, nil)
    guard status == errSecSuccess else { throw Failure(message: "Cannot save the Keychain item (\(status))") }
    _ = withoutKeychainDialogs {
        for other in keychainItems() where other.account != ownAccount { SecItemDelete(keychainQuery(other.account) as CFDictionary) }
    }
    try? FileManager.default.removeItem(at: previousBuild)
}

/// This build's item, or with `all` every build's (all created at this path, so no dialog either).
func keychainDelete(all: Bool = false) {
    #if BW_BROKER_TEST
    for account in all ? keychainItems().map(\.account) : [ownAccount] { try? FileManager.default.removeItem(atPath: testStore(account)) }
    return
    #endif
    _ = withoutKeychainDialogs {
        for account in all ? keychainItems().map(\.account) : [ownAccount] { SecItemDelete(keychainQuery(account) as CFDictionary) }
    }
}

// MARK: - Secure Enclave bundle

func hkdf(_ shared: SharedSecret, _ ephemeral: P256.KeyAgreement.PublicKey) -> SymmetricKey {
    shared.hkdfDerivedSymmetricKey(using: SHA256.self, salt: ephemeral.x963Representation,
                                   sharedInfo: Data("bw-broker v1".utf8), outputByteCount: 32)
}

func seal(_ passwords: [String: [String: String]]) throws -> [String: String] {
    #if BW_BROKER_TEST
    return ["fake": try JSONSerialization.data(withJSONObject: passwords).base64EncodedString()]
    #endif
    guard let access = SecAccessControlCreateWithFlags(nil, kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
                                                       [.privateKeyUsage, .biometryCurrentSet], nil) else {
        throw Failure(message: "Touch ID is not available")
    }
    let key = try SecureEnclave.P256.KeyAgreement.PrivateKey(accessControl: access)  // Fresh key per enrolment.
    let ephemeral = P256.KeyAgreement.PrivateKey()
    let box = try AES.GCM.seal(try JSONSerialization.data(withJSONObject: passwords),
                               using: hkdf(try ephemeral.sharedSecretFromKeyAgreement(with: key.publicKey),
                                           ephemeral.publicKey))
    return ["key": key.dataRepresentation.base64EncodedString(),
            "ephemeral": ephemeral.publicKey.x963Representation.base64EncodedString(),
            "box": box.combined!.base64EncodedString()]
}

enum Unseal { case cancelled, broken }

func unseal(_ sealed: [String: String], context: LAContext) throws -> [String: [String: String]] {
    #if BW_BROKER_TEST
    FileHandle.standardError.write(Data("touch: \(context.localizedReason)\n".utf8))
    switch testEnv["BW_BROKER_TEST_TOUCH"] {
    case "cancel": throw Unseal.cancelled
    case "broken-once":  // Broken until the renewal re-seals (as a new enclave key would).
        let marker = testEnv["BW_BROKER_TEST_STORE"]! + ".renewed"
        if !FileManager.default.fileExists(atPath: marker) {
            FileManager.default.createFile(atPath: marker, contents: nil)
            throw Unseal.broken
        }
        fallthrough
    default: return try JSONSerialization.jsonObject(with: Data(base64Encoded: sealed["fake"]!)!) as! [String: [String: String]]
    }
    #endif
    guard let keyData = Data(base64Encoded: sealed["key"] ?? ""),
          let ephemeralData = Data(base64Encoded: sealed["ephemeral"] ?? ""),
          let boxData = Data(base64Encoded: sealed["box"] ?? "") else { throw Unseal.broken }
    do {
        let key = try SecureEnclave.P256.KeyAgreement.PrivateKey(dataRepresentation: keyData, authenticationContext: context)
        let ephemeral = try P256.KeyAgreement.PublicKey(x963Representation: ephemeralData)
        let shared = try key.sharedSecretFromKeyAgreement(with: ephemeral)  // The Touch ID sheet appears here.
        let plain = try AES.GCM.open(AES.GCM.SealedBox(combined: boxData), using: hkdf(shared, ephemeral))
        guard let bundle = try JSONSerialization.jsonObject(with: plain) as? [String: [String: String]] else {
            throw Unseal.broken
        }
        return bundle
    } catch let error as LAError where [.userCancel, .systemCancel, .appCancel, .userFallback, .authenticationFailed]
                .contains(error.code) {
        throw Unseal.cancelled
    } catch let error as Unseal {
        throw error
    } catch {
        throw Unseal.broken  // Fingerprints changed (key invalidated) or damaged item.
    }
}
extension Unseal: Error {}

let phraseWords = ["amber", "anchor", "aspen", "badger", "basil", "beacon", "birch", "bison", "cedar", "cobalt",
                   "comet", "copper", "coral", "dune", "ember", "falcon", "fennel", "fjord", "garnet", "glacier",
                   "harbor", "hazel", "heron", "indigo", "ivory", "jasper", "juniper", "kestrel", "lagoon", "lantern",
                   "lilac", "lynx", "maple", "meadow", "mesa", "nectar", "nutmeg", "oasis", "olive", "orchid",
                   "otter", "pebble", "pepper", "pine", "plum", "quartz", "quill", "raven", "reef", "saffron",
                   "sage", "sierra", "spruce", "summit", "tamarind", "thistle", "tundra", "umber", "velvet", "violet",
                   "walnut", "willow", "yarrow", "zephyr"]

func newPhrase() -> String {
    (0..<3).map { _ in phraseWords[Int.random(in: 0..<phraseWords.count)] }.joined(separator: " ")
}

// MARK: - Bitwarden's signed CLI, one `bw serve` per vault over a private socketpair

func bitwardenBinary() throws -> String {
    #if BW_BROKER_TEST
    return testEnv["BW_BROKER_TEST_BW"]!
    #endif
    let path = here.appendingPathComponent("bw").path
    var code: SecStaticCode?
    var requirement: SecRequirement?
    guard SecStaticCodeCreateWithPath(URL(fileURLWithPath: path) as CFURL, [], &code) == errSecSuccess, let code,
          SecRequirementCreateWithString(bitwardenRequirement as CFString, [], &requirement) == errSecSuccess,
          SecStaticCodeCheckValidity(code, [], requirement) == errSecSuccess else {
        throw Failure(message: "Bitwarden CLI at \(path) is missing or not signed by Bitwarden Inc; rerun the installer")
    }
    return path
}

/// The spawned process itself must be Bitwarden's signed CLI: the file can be swapped between the static check and
/// the spawn (e.g. while the human types in the setup window).
func verifyRunning(_ pid: pid_t) -> Bool {
    #if BW_BROKER_TEST
    return true
    #endif
    var code: SecCode?
    var requirement: SecRequirement?
    return SecCodeCopyGuestWithAttributes(nil, [kSecGuestAttributePid: pid] as CFDictionary, [], &code) == errSecSuccess
        && SecRequirementCreateWithString(bitwardenRequirement as CFString, [], &requirement) == errSecSuccess
        && SecCodeCheckValidity(code!, [], requirement) == errSecSuccess
}

final class Serve {
    let vault: Vault
    private let binary: String
    private var pid: pid_t = 0
    private var fd: Int32 = -1
    private var closed = true  // Armed only once a verified process exists, so a failed init never recurses.

    init(_ vault: Vault, binary: String) throws {
        self.vault = vault
        self.binary = binary
        var pair: [Int32] = [0, 0]
        guard socketpair(AF_UNIX, SOCK_STREAM, 0, &pair) == 0 else { throw Failure(message: "socketpair failed") }
        var actions: posix_spawn_file_actions_t?
        posix_spawn_file_actions_init(&actions)
        defer { posix_spawn_file_actions_destroy(&actions) }
        posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0)
        posix_spawn_file_actions_addopen(&actions, 1, "/dev/null", O_WRONLY, 0)
        posix_spawn_file_actions_addopen(&actions, 2, "/dev/null", O_WRONLY, 0)
        posix_spawn_file_actions_adddup2(&actions, pair[1], 3)
        var attributes: posix_spawnattr_t?
        posix_spawnattr_init(&attributes)
        defer { posix_spawnattr_destroy(&attributes) }
        posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_CLOEXEC_DEFAULT))  // Only fds 0-3 reach bw.
        let environment = ProcessInfo.processInfo.environment
        var env = ["PATH=/usr/bin:/bin", "BW_NOINTERACTION=true"]
        for key in ["HOME", "USER", "LOGNAME", "LANG", "TMPDIR"] {
            if let value = environment[key] { env.append("\(key)=\(value)") }
        }
        if let appdata = vault.appdata { env.append("BITWARDENCLI_APPDATA_DIR=\(appdata)") }
        let argv = [binary, "serve", "--hostname", "fd+connected://3"]
        var cArgv = argv.map { strdup($0) } + [nil]
        var cEnv = env.map { strdup($0) } + [nil]
        defer { (cArgv + cEnv).forEach { free($0) } }
        let spawned = posix_spawn(&pid, binary, &actions, &attributes, &cArgv, &cEnv)
        close(pair[1])
        guard spawned == 0 else { close(pair[0]); throw Failure(message: "Cannot start Bitwarden CLI") }
        fd = pair[0]
        guard verifyRunning(pid) else {
            terminate()
            throw Failure(message: "The started Bitwarden CLI is not signed by Bitwarden Inc; nothing sent")
        }
        closed = false
        #if BW_BROKER_TEST
        var timeout = timeval(tv_sec: Int(testEnv["BW_BROKER_TEST_TIMEOUT"] ?? "60")!, tv_usec: 0)
        #else
        var timeout = timeval(tv_sec: 60, tv_usec: 0)
        #endif
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
    }

    func call(_ method: String, _ path: String, _ body: [String: Any]? = nil) throws -> [String: Any] {
        let payload = try body.map { try JSONSerialization.data(withJSONObject: $0) } ?? Data()
        var request = Data(("\(method) \(path) HTTP/1.1\r\nHost: localhost:8087\r\nContent-Type: application/json\r\n"
                            + "Content-Length: \(payload.count)\r\nConnection: keep-alive\r\n\r\n").utf8)
        request.append(payload)
        try request.withUnsafeBytes { raw in
            var sent = 0
            while sent < raw.count {
                let n = write(fd, raw.baseAddress! + sent, raw.count - sent)
                guard n > 0 else { throw Failure(message: "Bitwarden CLI connection closed") }
                sent += n
            }
        }
        var response = Data()
        var buffer = [UInt8](repeating: 0, count: 65536)
        var headerEnd: Range<Data.Index>?
        var length = -1
        while true {
            if headerEnd == nil, let end = response.range(of: Data("\r\n\r\n".utf8)) {
                headerEnd = end
                let header = String(decoding: response[..<end.lowerBound], as: UTF8.self).lowercased()
                guard let line = header.split(separator: "\r\n").first(where: { $0.hasPrefix("content-length:") }),
                      let value = Int(line.dropFirst("content-length:".count).trimmingCharacters(in: .whitespaces)) else {
                    throw Failure(message: "Unexpected Bitwarden CLI response")
                }
                length = value
            }
            if let end = headerEnd, response.count - end.upperBound >= length { break }
            let n = read(fd, &buffer, buffer.count)
            guard n > 0 else { throw Failure(message: "Bitwarden CLI did not answer") }
            response.append(contentsOf: buffer[0..<n])
        }
        let bodyData = response[headerEnd!.upperBound..<(headerEnd!.upperBound + length)]
        guard let json = try? JSONSerialization.jsonObject(with: bodyData) as? [String: Any] else {
            throw Failure(message: "Unexpected Bitwarden CLI response")
        }
        return json
    }

    func status() throws -> (String, String) {
        let reply = try call("GET", "/status")
        let template = ((reply["data"] as? [String: Any])?["template"] as? [String: Any]) ?? [:]
        return ((template["status"] as? String) ?? "unknown", ((template["userEmail"] as? String) ?? "").lowercased())
    }

    /// Locked, right account, fresh encrypted cache: ready for an unlock after the human approves.
    func prepare() throws {
        let (state, email) = try status()
        if state == "unauthenticated" { throw Failure(message: "\(vault.name): CLI logged out; run `bw-once --vault \(vault.name) login`") }
        guard state == "locked" else { throw Failure(message: "\(vault.name): CLI must be locked (status \(state))") }
        guard email == vault.email else { throw Failure(message: "\(vault.name): CLI is signed in as another account") }
        _ = try? call("POST", "/sync")  // Stale cache beats no answer; sync failure is not fatal.
    }

    func unlock(_ password: String) throws -> Bool {
        (try call("POST", "/unlock", ["password": password]))["success"] as? Bool == true
    }

    func items() throws -> [[String: Any]] {
        let reply = try call("GET", "/list/object/items")
        guard reply["success"] as? Bool == true,
              let data = (reply["data"] as? [String: Any])?["data"] as? [[String: Any]] else {
            throw Failure(message: "\(vault.name): cannot list items")
        }
        return data
    }

    func totp(_ id: String) throws -> String {
        let reply = try call("GET", "/object/totp/\(id)")
        guard let code = ((reply["data"] as? [String: Any])?["data"] as? String),
              code.range(of: #"^[0-9]{6,8}$"#, options: .regularExpression) != nil else {
            throw Failure(message: "No valid generated TOTP code")
        }
        return code
    }

    deinit { if !closed { _ = lockAndClose() } }

    /// Lock and prove it; on any doubt, a separate `bw lock` recovers. Always ends the process; idempotent.
    @discardableResult
    func lockAndClose() -> Bool {
        if closed { return lockedResult }
        closed = true
        var locked = false
        if (try? call("POST", "/lock")) != nil, let (state, _) = try? status() { locked = state == "locked" }
        terminate()
        if !locked { locked = recoverLock() }
        lockedResult = locked
        return locked
    }
    private var lockedResult = false

    private func recoverLock() -> Bool {
        guard let serve = try? Serve(vault, binary: binary) else { return false }
        serve.closed = true  // Its own cleanup is this function.
        defer { serve.terminate() }
        _ = try? serve.call("POST", "/lock")
        return (try? serve.status().0) == "locked"
    }

    func terminate() {
        if fd >= 0 { close(fd); fd = -1 }
        guard pid > 0 else { return }
        kill(pid, SIGTERM)
        for _ in 0..<50 {
            var status: Int32 = 0
            if waitpid(pid, &status, WNOHANG) == pid { pid = 0; return }
            usleep(20_000)
        }
        kill(pid, SIGKILL)
        var status: Int32 = 0
        waitpid(pid, &status, 0)
        pid = 0
    }
}

// MARK: - Matching (same rules as the front end's `matching`)

func matches(_ item: [String: Any], host: String) -> Bool {
    guard item["type"] as? Int == 1, let login = item["login"] as? [String: Any],
          let uris = login["uris"] as? [[String: Any]] else { return false }
    for entry in uris {
        guard let raw = entry["uri"] as? String, !raw.isEmpty else { continue }
        let value = raw.contains("://") || raw.hasPrefix("//") ? raw : "//" + raw
        guard let parts = URLComponents(string: value), ["", "http", "https"].contains(parts.scheme?.lowercased() ?? ""),
              parts.user == nil, parts.password == nil, parts.host?.lowercased() == host else { continue }
        return true
    }
    return false
}

// MARK: - Clipboard (written here: no other binary ever receives a released secret)

let ownerType = NSPasteboard.PasteboardType("org.bw-once.owner")

/// The released value to its destination; returns what the agent needs (the clear timer, or the one-time fill URL).
func deliver(_ secret: String, _ request: Request, to: String? = nil) throws -> [String: Any] {
    if (to ?? request.to) == "page" { return try deliverToPage(secret, host: request.host) }
    try copyToClipboard(secret)
    return ["clear_after_seconds": clipboardSeconds]
}

func copyToClipboard(_ secret: String) throws {
    #if BW_BROKER_TEST
    try Data(secret.utf8).write(to: here.appendingPathComponent("clip"))
    return
    #endif
    let board = NSPasteboard.general
    let item = NSPasteboardItem()
    let token = UUID().uuidString
    item.setString(secret, forType: .string)
    item.setString(token, forType: ownerType)
    item.setData(Data(), forType: NSPasteboard.PasteboardType("org.nspasteboard.ConcealedType"))
    item.setData(Data(), forType: NSPasteboard.PasteboardType("org.nspasteboard.TransientType"))
    board.clearContents()
    guard board.writeObjects([item]) else { throw Failure(message: "Clipboard delivery failed") }
    // The clear timer is this same binary in a detached child that only knows the token and change count.
    var pid: pid_t = 0
    var attributes: posix_spawnattr_t?
    posix_spawnattr_init(&attributes)
    defer { posix_spawnattr_destroy(&attributes) }
    posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_SETSID | POSIX_SPAWN_CLOEXEC_DEFAULT))
    var actions: posix_spawn_file_actions_t?
    posix_spawn_file_actions_init(&actions)
    defer { posix_spawn_file_actions_destroy(&actions) }
    for fd in Int32(0)...2 { posix_spawn_file_actions_addopen(&actions, fd, "/dev/null", fd == 0 ? O_RDONLY : O_WRONLY, 0) }
    let me = here.appendingPathComponent("bw-broker").path
    let arguments: [String] = [me, "--clear-after", String(clipboardSeconds), token, String(board.changeCount)]
    var argv: [UnsafeMutablePointer<CChar>?] = arguments.map { strdup($0) }
    argv.append(nil)
    var env: [UnsafeMutablePointer<CChar>?] = [strdup("PATH=/usr/bin:/bin"), nil]
    defer { (argv + env).forEach { free($0) } }
    _ = posix_spawn(&pid, me, &actions, &attributes, &argv, &env)  // Best effort, like any clipboard clear.
}

// MARK: - Page fill (`--to page`): no clipboard, works in a background browser tab

/// The value goes to a detached copy of this binary that serves it once over loopback, only to a page whose Origin is
/// exactly https://<host> and only at an unguessable path; the agent's `preview_evaluate` fetches it straight into
/// the field and returns its length. The clipboard path needs a focused tab: T3 drops Cmd+V into a hidden one.
func deliverToPage(_ secret: String, host: String) throws -> [String: Any] {
    let token = (0..<16).map { _ in String(format: "%02x", UInt8.random(in: 0...255)) }.joined()
    // Own session (like the clipboard clear timer): outlives this process and the agent tool's process group.
    var toChild: [Int32] = [0, 0], fromChild: [Int32] = [0, 0]
    guard pipe(&toChild) == 0, pipe(&fromChild) == 0 else { throw Failure(message: "Page delivery failed") }
    var attributes: posix_spawnattr_t?
    posix_spawnattr_init(&attributes)
    defer { posix_spawnattr_destroy(&attributes) }
    posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_SETSID | POSIX_SPAWN_CLOEXEC_DEFAULT))
    var actions: posix_spawn_file_actions_t?
    posix_spawn_file_actions_init(&actions)
    defer { posix_spawn_file_actions_destroy(&actions) }
    posix_spawn_file_actions_adddup2(&actions, toChild[0], 0)
    posix_spawn_file_actions_adddup2(&actions, fromChild[1], 1)
    posix_spawn_file_actions_addopen(&actions, 2, "/dev/null", O_WRONLY, 0)
    let me = here.appendingPathComponent("bw-broker").path
    var argv: [UnsafeMutablePointer<CChar>?] = [strdup(me), strdup("--serve-once"), nil]
    var env: [UnsafeMutablePointer<CChar>?] = [strdup("PATH=/usr/bin:/bin"), nil]
    defer { (argv + env).forEach { free($0) } }
    var pid: pid_t = 0
    let spawned = posix_spawn(&pid, me, &actions, &attributes, &argv, &env) == 0
    close(toChild[0])
    close(fromChild[1])
    let input = FileHandle(fileDescriptor: toChild[1], closeOnDealloc: true)
    let output = FileHandle(fileDescriptor: fromChild[0], closeOnDealloc: true)
    // The path can be swapped after our own start: only a child running this very build gets the value.
    guard spawned, isThisBuild(pid) else {
        if spawned { kill(pid, SIGKILL) }
        throw Failure(message: "Page delivery failed")
    }
    input.write(try JSONSerialization.data(withJSONObject: ["value": secret, "token": token, "origin": "https://" + host]))
    try? input.close()
    guard let port = Int(String(decoding: output.readDataToEndOfFile(), as: UTF8.self)
        .trimmingCharacters(in: .whitespacesAndNewlines)) else { throw Failure(message: "Page delivery failed") }
    return ["fill_url": "http://127.0.0.1:\(port)/\(token)", "fill_expires_in": fillSeconds]
}

func isThisBuild(_ pid: pid_t) -> Bool {
    #if BW_BROKER_TEST
    return testEnv["BW_BROKER_TEST_SWAPPED_CHILD"] != "1"
    #endif
    var code: SecCode?
    return SecCodeCopyGuestWithAttributes(nil, [kSecGuestAttributePid: pid] as CFDictionary, [], &code) == errSecSuccess
        && code.flatMap { SecCodeCheckValidity($0, [], nil) == errSecSuccess
            ? cdhash(unsafeBitCast($0, to: SecStaticCode.self)) : nil }.map { "broker-" + $0 } == ownAccount
}

/// `bw-broker --serve-once` (stdin: value, token, origin): prints its port, answers one matching GET, then exits.
func serveOnce() -> Never {
    guard let job = try? JSONSerialization.jsonObject(with: FileHandle.standardInput.readDataToEndOfFile()) as? [String: String],
          let value = job["value"], let token = job["token"], let origin = job["origin"] else { exit(2) }
    let server = socket(AF_INET, SOCK_STREAM, 0)
    var address = sockaddr_in()
    address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
    address.sin_family = sa_family_t(AF_INET)
    address.sin_addr.s_addr = inet_addr("127.0.0.1")
    var size = socklen_t(MemoryLayout<sockaddr_in>.size)
    guard withUnsafeMutablePointer(to: &address, { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        bind(server, $0, size) == 0 && listen(server, 8) == 0 && getsockname(server, $0, &size) == 0 } }) else { exit(1) }
    print(UInt16(bigEndian: address.sin_port))
    fflush(stdout)
    let null = open("/dev/null", O_WRONLY)
    dup2(null, 1)
    let deadline = Date().addingTimeInterval(Double(fillSeconds))
    while Date() < deadline {
        var poller = pollfd(fd: server, events: Int16(POLLIN), revents: 0)
        guard poll(&poller, 1, 500) > 0 else { continue }
        let client = accept(server, nil, nil)
        guard client >= 0 else { continue }
        var timeout = timeval(tv_sec: 0, tv_usec: 250_000)
        setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
        var head = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while head.count < 16_384, head.range(of: Data("\r\n\r\n".utf8)) == nil, Date() < deadline {
            let count = read(client, &buffer, buffer.count)
            if count <= 0 { break }
            head.append(buffer, count: count)
        }
        let lines = String(decoding: head, as: UTF8.self).components(separatedBy: "\r\n")
        let start = lines.first?.split(separator: " ").map(String.init) ?? []
        let headers = Dictionary(lines.dropFirst().compactMap { line -> (String, String)? in
            guard let colon = line.firstIndex(of: ":") else { return nil }
            return (line[..<colon].lowercased(), line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces))
        }, uniquingKeysWith: { first, _ in first })
        // Exact origin (the approved host's page over https) and path; a preflight (private network) never consumes.
        let allowed = start.count == 3 && start[1] == "/" + token && headers["origin"] == origin && Date() < deadline
        let method = start.first ?? ""
        let body = allowed && method == "GET" ? value : ""
        var reply = allowed && method == "GET" ? "HTTP/1.1 200 OK\r\n" : allowed && method == "OPTIONS"
            ? "HTTP/1.1 204 No Content\r\nAccess-Control-Allow-Methods: GET\r\nAccess-Control-Allow-Private-Network: true\r\n"
            : "HTTP/1.1 403 Forbidden\r\n"
        if allowed { reply += "Access-Control-Allow-Origin: \(origin)\r\nVary: Origin\r\n" }
        reply += "Cache-Control: no-store\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: \(body.utf8.count)\r\n"
            + "Connection: close\r\n\r\n" + body
        _ = reply.withCString { write(client, $0, strlen($0)) }
        close(client)
        if !body.isEmpty { exit(0) }
    }
    exit(0)
}

/// `bw-broker --clear-after SECONDS TOKEN CHANGECOUNT`: clear only our unchanged write (a newer copy stays).
func clearLater(_ arguments: [String]) -> Never {
    guard arguments.count == 5, let seconds = Double(arguments[2]), let count = Int(arguments[4]) else { exit(2) }
    Thread.sleep(forTimeInterval: seconds)
    let board = NSPasteboard.general
    if board.changeCount == count && board.string(forType: ownerType) == arguments[3] { board.clearContents() }
    exit(0)
}

// MARK: - Mutex shared with the Python front end (~/.cache/bw-once/lock-<vault>)

func lockVaults(_ vaults: [Vault]) throws -> [Int32] {
    let home = ProcessInfo.processInfo.environment["HOME"].map { URL(fileURLWithPath: $0) }
        ?? FileManager.default.homeDirectoryForCurrentUser  // Same directory as the front end's Path.home().
    let cache = home.appendingPathComponent(".cache/bw-once")
    try FileManager.default.createDirectory(at: cache, withIntermediateDirectories: true,
                                            attributes: [.posixPermissions: 0o700])
    var fds: [Int32] = []
    for vault in vaults {
        let fd = open(cache.appendingPathComponent("lock-\(vault.name)").path, O_CREAT | O_RDWR | O_NOFOLLOW, 0o600)
        guard fd >= 0, flock(fd, LOCK_EX | LOCK_NB) == 0 else {
            fds.forEach { close($0) }
            throw Failure(message: "Another bw-once request is running for \(vault.name)")
        }
        fds.append(fd)
    }
    return fds
}

// MARK: - Panel

final class Panel: NSObject, NSWindowDelegate {
    let window: NSPanel
    let stack = NSStackView()
    let status = NSTextField(labelWithString: "")
    var onCancel: () -> Void = {}
    private var buttons = NSStackView()
    private var fields: [String: NSSecureTextField] = [:]

    init(title: String) {
        window = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 520, height: 200),
                         styleMask: [.titled, .closable], backing: .buffered, defer: false)
        super.init()
        window.title = title
        // Agents call from the background: show on the current Space (also over a full-screen app), in front.
        window.level = .modalPanel
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.hidesOnDeactivate = false
        window.isReleasedWhenClosed = false
        window.delegate = self
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        stack.edgeInsets = NSEdgeInsets(top: 18, left: 20, bottom: 18, right: 20)
        window.contentView = stack
        buttons.orientation = .horizontal
        buttons.spacing = 8
    }

    func line(_ value: String, color: NSColor = .labelColor, size: CGFloat = 13, mono: Bool = false) {
        let label = NSTextField(wrappingLabelWithString: value)
        label.font = mono ? .monospacedSystemFont(ofSize: size, weight: .regular) : .systemFont(ofSize: size)
        label.textColor = color
        label.preferredMaxLayoutWidth = 480
        stack.addArrangedSubview(label)
    }

    func box(_ title: String, _ rows: [(String, String)], tint: NSColor) {
        let box = NSBox()
        box.title = title
        box.titleFont = .boldSystemFont(ofSize: 11)
        box.borderColor = tint
        box.boxType = .custom
        box.borderWidth = 1
        box.cornerRadius = 6
        let grid = NSGridView(views: rows.map { row -> [NSView] in
            let key = NSTextField(labelWithString: row.0)
            key.textColor = .secondaryLabelColor
            let value = NSTextField(wrappingLabelWithString: row.1)
            value.preferredMaxLayoutWidth = 380
            return [key, value]
        })
        grid.rowSpacing = 4
        grid.columnSpacing = 10
        box.contentView = grid
        box.contentViewMargins = NSSize(width: 10, height: 8)
        stack.addArrangedSubview(box)
        box.widthAnchor.constraint(equalToConstant: 480).isActive = true
    }

    func secureField(_ key: String, label: String) {
        line(label, color: .secondaryLabelColor, size: 12)
        let field = NSSecureTextField()
        field.widthAnchor.constraint(equalToConstant: 480).isActive = true
        fields[key] = field
        stack.addArrangedSubview(field)
    }

    func value(_ key: String) -> String { fields[key]?.stringValue ?? "" }

    func button(_ title: String, primary: Bool = false, action: @escaping () -> Void) {
        let button = ClosureButton(title: title, action: action)
        if primary { button.keyEquivalent = "\r" }
        if title == "Cancel" { button.keyEquivalent = "\u{1b}" }
        buttons.addArrangedSubview(button)
    }

    /// `activate: false`: an informational window that never takes focus from what the human is typing.
    func show(activate: Bool = true) {
        status.textColor = .secondaryLabelColor
        stack.addArrangedSubview(status)
        stack.addArrangedSubview(buttons)
        #if BW_BROKER_TEST
        // Hidden: record what the human would read, type the test passwords, press the primary button.
        let texts = stack.arrangedSubviews.flatMap { view -> [String] in
            if let box = view as? NSBox { return [box.title] + (box.contentView?.subviews.compactMap { ($0 as? NSTextField)?.stringValue } ?? []) }
            return [(view as? NSTextField)?.stringValue].compactMap { $0 }
        }
        FileHandle.standardError.write(Data(("panel: " + texts.joined(separator: " | ") + "\n").utf8))
        if let typed = testEnv["BW_BROKER_TEST_TYPE"].flatMap({ try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: String] }) {
            for (key, field) in fields { field.stringValue = typed[key] ?? "" }
        }
        for case let button as NSButton in buttons.arrangedSubviews where button.keyEquivalent == "\r" {
            DispatchQueue.main.async { button.performClick(nil) }
        }
        return
        #endif
        window.layoutIfNeeded()
        window.setContentSize(stack.fittingSize)
        window.center()
        if activate { NSApp.activate(ignoringOtherApps: true) }
        window.orderFrontRegardless()
        if activate { window.makeKey() }
        if let first = fields.values.first { window.makeFirstResponder(first) }
    }

    func setStatus(_ value: String, color: NSColor = .secondaryLabelColor) {
        #if BW_BROKER_TEST
        FileHandle.standardError.write(Data(("status: " + value + "\n").utf8))
        #endif
        status.stringValue = value
        status.textColor = color
        window.setContentSize(stack.fittingSize)
    }

    func setButtons(enabled: Bool) {
        for case let button as NSButton in buttons.arrangedSubviews { button.isEnabled = enabled }
    }

    func windowWillClose(_ notification: Notification) { onCancel() }

    /// Close for good: empty the password fields and drop the buttons, whose handlers capture this panel and the
    /// passwords typed or already known (a retain cycle would otherwise keep them for the process lifetime).
    func dispose() {
        onCancel = {}
        fields.values.forEach { $0.stringValue = "" }
        fields = [:]
        buttons.arrangedSubviews.forEach { $0.removeFromSuperview() }
        window.close()
    }
}

final class ClosureButton: NSButton {
    private let handler: () -> Void
    init(title: String, action: @escaping () -> Void) {
        handler = action
        super.init(frame: .zero)
        self.title = title
        bezelStyle = .rounded
        target = self
        self.action = #selector(fire)
    }
    required init?(coder: NSCoder) { nil }
    @objc func fire() { handler() }
}

func onMain(_ block: @escaping () -> Void) { DispatchQueue.main.async(execute: block) }

/// Cancel (window closed, Esc, watchdog) versus release: whichever comes first wins, never both.
final class Gate {
    private let mutex = NSLock()
    private var cancelled = false, committed = false
    var isCancelled: Bool { mutex.lock(); defer { mutex.unlock() }; return cancelled }
    func cancel() { mutex.lock(); if !committed { cancelled = true }; mutex.unlock() }
    func commit() -> Bool { mutex.lock(); defer { mutex.unlock() }; if !cancelled { committed = true }; return committed }
}

// MARK: - Enrolment (also the renewal path: phrase shown, so a fake "type your password" window stands out)

/// `known`: passwords already in memory (kept as they are). `mergeExisting`: blank fields keep the saved ones,
/// which needs one Touch ID; false when the saved seal is broken (fingerprints changed).
func enroll(_ request: Request, known: [String: [String: String]] = [:], mergeExisting: Bool = true,
            reason: String? = nil, then: (() -> Void)? = nil) {
    let binary: String
    do { binary = try bitwardenBinary() } catch let error as Failure { fail(error.message) } catch { fail("\(error)") }
    // An unreadable item (e.g. the post-update Keychain prompt denied) must never turn into a new phrase.
    withKeychainItem { loaded in
        let existing: [String: Any]?
        do { existing = try loaded.get() } catch let error as Failure {
            fail(error.message + "; nothing changed (allow the Keychain prompt, or `bw-once touchid forget` to start over)")
        } catch { fail("Cannot read the bw-once Keychain item; nothing changed") }
        enrollPanel(request, existing: existing, binary: binary, known: known, mergeExisting: mergeExisting,
                    reason: reason, then: then)
    }
}

func enrollPanel(_ request: Request, existing: [String: Any]?, binary: String, known: [String: [String: String]],
                 mergeExisting: Bool, reason: String?, then: (() -> Void)?) {
    let phrase = (existing?["phrase"] as? String) ?? newPhrase()
    let saved = Set(((existing?["vaults"] as? [[String: String]]) ?? []).compactMap { $0["name"] })
    let panel = Panel(title: "bw-once · Touch ID setup")
    if existing == nil {
        panel.line("NEW phrase: remember it (it becomes yours when you press Save):", color: .systemOrange, size: 12)
    } else {
        panel.line("Your bw-once phrase:", color: .secondaryLabelColor, size: 12)
    }
    panel.line(phrase, size: 20, mono: true)
    panel.line("From now on every genuine bw-once window shows this phrase. No phrase or other words → don't type or touch.",
               color: .secondaryLabelColor, size: 11)
    if let reason { panel.line(reason, color: .systemOrange) }
    let asked = request.vaults.filter { known[$0.name] == nil }
    for vault in asked {
        let keep = mergeExisting && saved.contains(vault.name)
        panel.secureField(vault.name, label: "Master password for \(vault.name) (\(vault.email))"
                          + (keep ? " · leave empty to keep the saved one" : " · leave empty to skip"))
    }
    panel.onCancel = { fail("Touch ID setup cancelled") }
    panel.button("Cancel") { panel.window.close() }
    panel.button("Save", primary: true) {
        panel.setButtons(enabled: false)
        panel.setStatus("Checking each password with Bitwarden…")
        let typed = Dictionary(uniqueKeysWithValues: asked.map { ($0.name, panel.value($0.name)) })
        DispatchQueue.global().async {
            do {
                var bundle: [String: [String: String]] = [:]
                let keepSaved = asked.contains { typed[$0.name, default: ""].isEmpty && saved.contains($0.name) }
                    || saved.contains { name in !request.vaults.contains { $0.name == name } }
                if mergeExisting && keepSaved, let sealed = existing?["sealed"] as? [String: String] {
                    let context = LAContext()
                    context.localizedReason = "keep your saved bw-once passwords"
                    bundle = try unseal(sealed, context: context)
                }
                bundle.merge(known) { _, new in new }
                let locks = try lockVaults(asked.filter { !typed[$0.name, default: ""].isEmpty })
                defer { locks.forEach { close($0) } }
                for vault in asked {
                    guard let password = typed[vault.name], !password.isEmpty else { continue }
                    let serve = try Serve(vault, binary: binary)
                    let accepted: Bool
                    do {
                        try serve.prepare()
                        accepted = try serve.unlock(password)
                    } catch {
                        serve.lockAndClose()  // E.g. unlock succeeded inside bw but its answer was lost.
                        throw error
                    }
                    guard serve.lockAndClose() else {
                        throw Failure(message: "\(vault.name): lock verification failed; run `bw lock`")
                    }
                    guard accepted else { throw Failure(message: "Bitwarden rejected the master password for \(vault.name)") }
                    bundle[vault.name] = ["email": vault.email, "password": password]
                }
                // A vault whose configured account changed must not keep the old account's password.
                bundle = bundle.filter { entry in
                    !request.vaults.contains { $0.name == entry.key && $0.email != entry.value["email"] }
                }
                guard !bundle.isEmpty else { throw Failure(message: "Type at least one master password") }
                try keychainSave(["v": 1, "phrase": phrase, "sealed": try seal(bundle),
                                  "vaults": bundle.keys.sorted().map { ["name": $0, "email": bundle[$0]!["email"]!] }])
                let names = bundle.keys.sorted()
                onMain {
                    panel.dispose()  // A request continues after a renewal (and may hold re-copies for minutes).
                    if let then { then() } else { finish(["ok": true, "enrolled": names]) }
                }
            } catch {
                let message = (error as? Failure)?.message ?? (error is Unseal ? "Touch ID cancelled" : "Setup failed")
                #if BW_BROKER_TEST
                fail(message)  // A human would correct the field and press Save again.
                #endif
                onMain { panel.setStatus(message, color: .systemRed); panel.setButtons(enabled: true) }
            }
        }
    }
    panel.show()
}

// MARK: - Request (list / copy)

func describe(_ request: Request, vaults: [String]) -> [(String, String)] {
    var what: String
    switch request.op {
    case "list": what = "names and usernames of matching logins" + (request.username.map { " with username \($0)" } ?? "")
        + " (no secrets)"
    default:
        what = "\(request.field) of " + (request.username.map { "login \($0)" } ?? request.id.map { "item \($0)" }
            ?? (request.field == "totp" ? "the only matching login"
                : "one matching login; if several match, the agent picks one (shown here)"))
    }
    var rows = [("Releases", what), ("Exact host", request.host), ("Searches", vaults.joined(separator: ", ")),
                ("Goes to", request.op != "copy" ? "the agent (metadata)" : request.to == "page"
                    ? "a page on https://\(request.host) only (one fetch within \(fillSeconds) s), not the clipboard"
                    : "clipboard, cleared after \(clipboardSeconds) s")]
    if recopyAllowed(request) {
        rows.append(("Re-copies", "the same login's \(request.field) for this thread (page or clipboard), "
                     + "\(Int(recopySeconds / 60)) min, no touch (each one shown)"))
    }
    return rows
}

func recopyAllowed(_ request: Request) -> Bool {
    request.op == "copy" && request.field != "totp" && request.thread != nil  // A TOTP code goes stale.
}

/// Socket name shared with the front end (`bw_once.recopy_socket`): host, field and thread, hashed to fit the path.
func recopyKey(host: String, field: String, thread: String) -> String {
    "recopy-" + SHA256.hash(data: Data([host, field, thread].joined(separator: "\n").utf8))
        .map { String(format: "%02x", $0) }.joined().prefix(32)
}

struct RecopySocket { let fd: Int32, path: String, inode: ino_t }

/// The release itself: binds the re-copy socket (replacing an older holder's for the same key, which notices and
/// exits) and writes the clipboard under one lock, so of two releases for one key the later wins both. Bound before
/// the answer, so the agent's next call already finds it.
func deliverAndOpenRecopy(_ request: Request, _ secret: String) throws -> (RecopySocket?, [String: Any]) {
    guard recopyAllowed(request) else { return (nil, try deliver(secret, request)) }
    let key = recopyKey(host: request.host, field: request.field, thread: request.thread ?? "")
    return try withRecopyLock(key) {
        unlink(socketPath(key))
        var socket: RecopySocket?
        if let (fd, path) = try? privateSocket(key) {
            var own = stat()
            stat(path, &own)
            socket = RecopySocket(fd: fd, path: path, inode: own.st_ino)
        }
        do { return (socket, try deliver(secret, request)) } catch {
            if let socket { close(socket.fd); unlink(socket.path) }
            throw error
        }
    }
}

/// Replacement (new holder binds) and delivery (a holder checks it still owns the path, then copies) take this
/// lock, so a replaced holder can never overwrite the newer login's clipboard write.
func withRecopyLock<T>(_ key: String, _ body: () throws -> T) rethrows -> T {
    let fd = open(String(socketPath(key).dropLast(5)) + ".lock", O_CREAT | O_RDWR | O_NOFOLLOW, 0o600)
    if fd >= 0 { flock(fd, LOCK_EX) }
    defer { if fd >= 0 { close(fd) } }
    return try body()
}

func ownsPath(_ socket: RecopySocket) -> Bool {
    var current = stat()
    return stat(socket.path, &current) == 0 && current.st_ino == socket.inode
}

/// After a release: keep only that login's field in memory and re-copy it for the same thread, host and field
/// when the agent names the same login (`--id` or `--username`), each time in a small window that takes no
/// focus. A newer copy for the same key replaces this holder. Vaults stay locked throughout. Never returns.
func holdForRecopies(_ socket: RecopySocket, _ request: Request, _ meta: [String: Any], _ secret: String, phrase: String,
                     until deadline: Date) -> Never {
    var value: String? = secret
    let (server, path) = (socket.fd, socket.path)
    let until = DateFormatter.localizedString(from: deadline, dateStyle: .none, timeStyle: .short)
    let name = meta["name"] as? String ?? "?", username = meta["username"] as? String
    var shown = Date.distantPast
    let key = recopyKey(host: request.host, field: request.field, thread: request.thread ?? "")
    while Date() < deadline {
        guard ownsPath(socket) else { break }  // Replaced or removed.
        var poller = pollfd(fd: server, events: Int16(POLLIN), revents: 0)
        guard poll(&poller, 1, Int32(min(500, max(1, deadline.timeIntervalSinceNow * 1000)))) > 0 else { continue }
        let client = accept(server, nil, nil)
        guard client >= 0 else { continue }
        let ask = readRequestLine(client, until: deadline) ?? [:]
        let id = (ask["id"] as? String)?.lowercased(), user = (ask["username"] as? String)?.lowercased()
        guard (ask["host"] as? String)?.lowercased() == request.host, ask["field"] as? String == request.field,
              ask["thread"] as? String == request.thread, id != nil || user != nil,
              id == nil || id == meta["id"] as? String, user == nil || user == username?.lowercased(),
              (ask["vaults"] as? [String])?.contains(meta["vault"] as? String ?? "") == true, let secret = value else {
            reply(client, ["ok": false, "miss": true])
            continue
        }
        let to = ask["to"] as? String == "page" ? "page" : "clipboard"
        let delivered: Result<[String: Any], Error>? = withRecopyLock(key) {
            guard Date() < deadline, ownsPath(socket) else { return nil }
            return Result { try deliver(secret, request, to: to) }
        }
        guard case .success(let destination) = delivered else {
            reply(client, delivered == nil ? ["ok": false, "miss": true] : ["ok": false, "error": "Delivery failed"])
            continue
        }
        reply(client, ["ok": true, "copied": request.field, "recopy": true, "touch": false,
                       "recopy_until": ISO8601DateFormatter().string(from: deadline)].merging(meta) { $1 }.merging(destination) { $1 })
        shown = Date()
        onMain {
            let notice = Panel(title: "bw-once · re-copy (no touch)")
            notice.line("Your bw-once phrase:", color: .secondaryLabelColor, size: 11)
            notice.line(phrase, size: 18, mono: true)
            notice.line((to == "page" ? "Sent " : "Copied ") + "\(request.field) of \(name) (\(username ?? "no username"), \(meta["vault"] as? String ?? "?")) "
                        + "again (\(to == "page" ? "to the https://\(request.host) page" : "clipboard")) for thread \(request.thread ?? "?"). You approved this login with Touch ID; re-copies end \(until).")
            notice.show(activate: false)
            DispatchQueue.main.asyncAfter(deadline: .now() + 4) { notice.window.close() }
        }
    }
    value = nil
    close(server)
    withRecopyLock(key) { if ownsPath(socket) { unlink(path) } }
    Thread.sleep(forTimeInterval: max(0, 4.5 + shown.timeIntervalSinceNow))  // Let a last notice finish.
    exit(0)
}

/// Vaults are locked; only the matching logins' field values live here. Never returns.
func awaitPick(_ request: Request, _ choices: [([String: Any], String)], panel: Panel, gate: Gate,
               base: [String: Any], phrase: String) -> Never {
    var choices = choices
    let token = (0..<16).map { _ in String(format: "%02x", UInt8.random(in: 0...255)) }.joined()
    let (server, path) = (try? privateSocket("pick-\(token)")) ?? (-1, "")
    if server < 0 { fail("Cannot open the pick socket; nothing released") }
    func closeSocket() { close(server); unlink(path) }  // Every exit path below; exit() skips defers.
    func label(_ meta: [String: Any]) -> String {
        "\(meta["name"] as? String ?? "?") (\(meta["username"] as? String ?? "no username"), \(meta["vault"] as? String ?? "?"))"
    }
    onMain {
        panel.setStatus("Vault locked. \(choices.count) logins match; the agent picks one within \(Int(pickSeconds)) s:\n"
                        + choices.map { "• " + label($0.0) }.joined(separator: "\n"))
    }
    emit(base.merging(["pick": ["token": token, "expires_in": Int(pickSeconds), "candidates": choices.map(\.0),
                                "next": "bw-once pick --token \(token) --id <id>"]]) { $1 })
    let deadline = Date().addingTimeInterval(pickSeconds)
    while Date() < deadline && !gate.isCancelled {
        var poller = pollfd(fd: server, events: Int16(POLLIN), revents: 0)
        guard poll(&poller, 1, Int32(min(500, max(1, deadline.timeIntervalSinceNow * 1000)))) > 0 else { continue }
        let client = accept(server, nil, nil)
        guard client >= 0 else { continue }
        guard let ask = readRequestLine(client, until: deadline), let id = (ask["id"] as? String)?.lowercased(),
              let index = choices.firstIndex(where: { ($0.0["id"] as? String) == id }) else {
            reply(client, ["ok": false, "error": "Unknown --id; pick one of the listed candidates"])
            continue
        }
        guard Date() < deadline else { reply(client, ["ok": false, "error": "Pick expired"]); break }
        guard gate.commit() else { reply(client, ["ok": false, "error": "Request cancelled"]); break }
        let (meta, value) = choices[index]
        choices = []
        closeSocket()
        let recopyUntil = Date().addingTimeInterval(recopySeconds)
        let recopy: RecopySocket?, destination: [String: Any]
        do { (recopy, destination) = try deliverAndOpenRecopy(request, value) } catch {
            reply(client, ["ok": false, "error": "Delivery failed"])
            fail("Delivery failed")
        }
        var answer: [String: Any] = ["ok": true, "copied": request.field].merging(destination) { $1 }
        if recopy != nil { answer["recopy_until"] = ISO8601DateFormatter().string(from: recopyUntil) }
        reply(client, answer.merging(meta) { $1 })
        onMain {
            panel.onCancel = {}
            panel.setStatus("✓ Agent picked \(label(meta)) · copied \(request.field) · vault locked", color: .systemGreen)
            DispatchQueue.main.asyncAfter(deadline: .now() + resultSeconds) {
                if recopy != nil { panel.window.close() } else { exit(0) }
            }
        }
        if let recopy { holdForRecopies(recopy, request, meta, value, phrase: phrase, until: recopyUntil) }
        while true { sleep(60) }  // The main queue exits.
    }
    choices = []
    closeSocket()
    let why = gate.isCancelled ? "Request cancelled" : "No pick within \(Int(pickSeconds)) s"
    onMain {
        panel.onCancel = {}
        panel.setStatus("\(why); nothing released", color: .systemOrange)
        DispatchQueue.main.asyncAfter(deadline: .now() + resultSeconds) { exit(1) }
    }
    while true { sleep(60) }
}

func serveRequest(_ request: Request) {
    let binary: String
    do { binary = try bitwardenBinary() } catch let error as Failure { fail(error.message) } catch { fail("\(error)") }
    withKeychainItem { loaded in
        let item: [String: Any]
        do {
            guard let value = try loaded.get() else { fail("Touch ID not set up; run `bw-once touchid enroll`") }
            item = value
        } catch let error as Failure { fail(error.message) } catch { fail("\(error)") }
        serveRequest(request, item: item, binary: binary)
    }
}

func serveRequest(_ request: Request, item: [String: Any], binary: String) {
    let enrolled = Set(((item["vaults"] as? [[String: String]]) ?? []).compactMap { $0["name"] })
    let vaults = request.vaults.filter { enrolled.contains($0.name) }
    let skipped = request.vaults.filter { !enrolled.contains($0.name) }.map { ["vault": $0.name, "reason": "not enrolled"] }
    guard !vaults.isEmpty else { fail("None of the requested vaults is enrolled for Touch ID") }

    let panel = Panel(title: "bw-once · Bitwarden request")
    panel.line("Your bw-once phrase:", color: .secondaryLabelColor, size: 11)
    panel.line(item["phrase"] as? String ?? "?", size: 18, mono: true)
    var claim: [(String, String)] = []
    if let thread = request.thread { claim.append(("Thread", thread)) }
    if let why = request.why { claim.append(("Why", why)) }
    if claim.isEmpty { claim.append(("", "no reason given")) }
    panel.box("AGENT SAYS (unverified)", claim, tint: .systemOrange)
    panel.box("BW-ONCE WILL (checked)", describe(request, vaults: vaults.map(\.name)), tint: .systemGreen)
    panel.line("Touch ID approves exactly the green box.", color: .secondaryLabelColor, size: 11)

    let context = LAContext()
    context.localizedReason = "approve the bw-once request shown on screen"
    let gate = Gate()
    var serves: [Serve] = []
    var locks: [Int32] = []
    func cleanup() -> Bool {
        let ok = serves.map { $0.lockAndClose() }.allSatisfy { $0 }  // Every vault, even after one failed.
        serves = []
        locks.forEach { close($0) }
        locks = []
        return ok
    }
    // The background thread owns the vault processes; cancel only flags and aborts the Touch ID sheet.
    panel.onCancel = {
        gate.cancel()
        context.invalidate()
    }
    DispatchQueue.main.asyncAfter(deadline: .now() + 300) { panel.onCancel(); panel.window.orderOut(nil) }
    panel.button("Cancel") { panel.window.close() }
    panel.show()
    panel.setStatus("Touch ID to approve…")

    DispatchQueue.global().async {
        do {
            locks = try lockVaults(vaults)
            // Prepare while the human reads: start each vault's CLI, check locked + account, sync.
            let group = DispatchGroup()
            var prepared: [String: Result<Serve, Error>] = [:]
            let guardLock = NSLock()
            for vault in vaults {
                group.enter()
                DispatchQueue.global().async {
                    let outcome = Result { () throws -> Serve in
                        let serve = try Serve(vault, binary: binary)
                        do { try serve.prepare() } catch { serve.lockAndClose(); throw error }
                        return serve
                    }
                    guardLock.lock(); prepared[vault.name] = outcome; guardLock.unlock()
                    group.leave()
                }
            }
            var bundle: [String: [String: String]]
            do {
                bundle = try unseal(item["sealed"] as? [String: String] ?? [:], context: context)
            } catch Unseal.cancelled {
                group.wait()
                serves = prepared.values.compactMap { try? $0.get() }
                _ = cleanup()
                fail("Request cancelled")
            } catch {
                group.wait()
                serves = prepared.values.compactMap { try? $0.get() }
                _ = cleanup()
                if gate.isCancelled { fail("Request cancelled") }
                onMain {
                    panel.onCancel = {}
                    panel.window.close()
                    enroll(request, mergeExisting: false,
                           reason: "Touch ID no longer opens your saved passwords (fingerprints changed?). "
                           + "Type them once to renew; the request continues afterwards.") { serveRequest(request) }
                }
                return
            }
            group.wait()
            if gate.isCancelled {
                serves = prepared.values.compactMap { try? $0.get() }
                _ = cleanup()
                fail("Request cancelled")
            }
            onMain { panel.setStatus("Approved · searching…") }
            var candidates: [(Vault, [String: Any], Serve)] = []
            var choices: [([String: Any], String)] = []  // (metadata, field value) when the agent must pick.
            var unavailable = skipped
            var rejected: [Vault] = []
            for vault in vaults {
                switch prepared[vault.name]! {
                case .failure(let error):
                    unavailable.append(["vault": vault.name, "reason": (error as? Failure)?.message ?? "unavailable"])
                case .success(let serve):
                    serves.append(serve)
                    guard let password = bundle[vault.name]?["password"], bundle[vault.name]?["email"] == vault.email,
                          try serve.unlock(password) else { rejected.append(vault); continue }
                    for entry in try serve.items() where matches(entry, host: request.host) {
                        candidates.append((vault, entry, serve))
                    }
                }
            }
            if !rejected.isEmpty {
                let keep = bundle.filter { entry in !rejected.contains { $0.name == entry.key } }
                bundle = [:]
                guard cleanup() else { throw Failure(message: "Lock verification failed; run `bw lock` now") }
                onMain {
                    panel.onCancel = {}
                    panel.window.close()
                    enroll(Request(op: "enroll", vaults: rejected), known: keep,
                           reason: "Bitwarden rejected the saved master password for "
                           + rejected.map(\.name).joined(separator: ", ") + " (changed?). Type it once to renew.") {
                        serveRequest(request)
                    }
                }
                return
            }
            bundle = [:]
            func metadata(_ entry: (Vault, [String: Any], Serve)) -> [String: Any] {
                let login = entry.1["login"] as? [String: Any]
                return ["vault": entry.0.name, "id": (entry.1["id"] as? String ?? "").lowercased(),
                        "name": entry.1["name"] as? String ?? "", "username": login?["username"] ?? NSNull(), "host": request.host]
            }
            var result: [String: Any] = ["ok": true, "searched": vaults.map(\.name).filter { name in !unavailable.contains { $0["vault"] == name } },
                                         "unavailable": unavailable]
            var secret: String?
            if request.op == "list" {
                result["items"] = candidates.filter { entry in
                    request.username == nil
                        || (((entry.1["login"] as? [String: Any])?["username"] as? String) ?? "").lowercased() == request.username
                }.map(metadata)
            } else {
                let picked = candidates.filter { entry in
                    let login = entry.1["login"] as? [String: Any]
                    return (request.id == nil || (entry.1["id"] as? String)?.lowercased() == request.id)
                        && (request.username == nil || ((login?["username"] as? String) ?? "").lowercased() == request.username)
                }
                if picked.count > 1 && request.field != "totp" {  // A TOTP code would go stale during the pick.
                    // Several logins and no --username/--id: keep only these logins' field, lock everything,
                    // and let the agent pick one (`bw-once pick`); the window shows its choice.
                    for entry in picked {
                        let login = entry.1["login"] as? [String: Any]
                        let value = login?[request.field] as? String
                        if let value, !value.isEmpty, !value.contains("\0") { choices.append((metadata(entry), value)) }
                    }
                    guard choices.count > 1 else { throw Failure(message: "Requested field is missing on the matching logins") }
                }
                guard picked.count == 1 || !choices.isEmpty, let chosen = picked.first else {
                    throw Failure(message: (picked.isEmpty ? "No exact-host login matches; check the saved Website URI: a parent domain does not match a subdomain. This does not establish that the account is absent from the vault" : "\(picked.count) logins match; pass --username or --id")
                        + (candidates.isEmpty ? "" : "; candidates: "
                        + candidates.map { "\($0.0.name)/\($0.1["name"] as? String ?? "?")/\((($0.1["login"] as? [String: Any])?["username"] as? String) ?? "-")" }
                        .joined(separator: ", ")))
                }
                if choices.isEmpty {
                    let login = chosen.1["login"] as? [String: Any]
                    switch request.field {
                    case "totp": secret = try chosen.2.totp((chosen.1["id"] as? String ?? "").lowercased())
                    default: secret = login?[request.field] as? String
                    }
                    guard let value = secret, !value.isEmpty, !value.contains("\0") else {
                        throw Failure(message: "Requested field is missing")
                    }
                    result.merge(metadata(chosen)) { $1 }
                    result["copied"] = request.field
                }
            }
            candidates = []
            #if BW_BROKER_TEST
            if testEnv["BW_BROKER_TEST_CANCEL_AFTER_SEARCH"] == "1" { panel.onCancel() }
            #endif
            guard cleanup() else { throw Failure(message: "Lock verification failed; nothing released; run `bw lock` now") }
            guard Date() < answerDeadline else {
                throw Failure(message: "Request took over \(Int(answerSeconds)) s; nothing released, ask again")
            }
            let phrase = item["phrase"] as? String ?? "?"
            if !choices.isEmpty { awaitPick(request, choices, panel: panel, gate: gate, base: result, phrase: phrase) }
            guard gate.commit() else { fail("Request cancelled") }  // Closed during the search: release nothing.
            let recopyUntil = Date().addingTimeInterval(recopySeconds)
            let delivered = try secret.map { try deliverAndOpenRecopy(request, $0) }
            let recopy = delivered?.0
            result.merge(delivered?.1 ?? [:]) { $1 }
            let kept = recopy == nil ? nil : secret
            if recopy != nil { result["recopy_until"] = ISO8601DateFormatter().string(from: recopyUntil) }
            secret = nil
            onMain {
                panel.onCancel = {}
                let what = request.op == "list" ? "\((result["items"] as? [Any])?.count ?? 0) login(s) listed"
                    : (request.to == "page" ? "Sent " : "Copied ") + "\(request.field) of \(result["name"] as? String ?? "?") (\(result["username"] as? String ?? "no username"), "
                      + "\(result["vault"] as? String ?? "?"))"
                panel.setStatus("✓ \(what) · vault locked", color: .systemGreen)
                DispatchQueue.main.asyncAfter(deadline: .now() + resultSeconds) {
                    guard let recopy, let kept else { finish(result) }
                    emit(result)  // The front end returns now; this process keeps only the one released field.
                    panel.window.close()
                    var meta = result
                    ["ok", "copied", "clear_after_seconds", "fill_url", "fill_expires_in", "recopy_until", "searched", "unavailable"]
                        .forEach { meta[$0] = nil }
                    DispatchQueue.global().async {
                        holdForRecopies(recopy, request, meta, kept, phrase: phrase, until: recopyUntil)
                    }
                }
            }
        } catch {
            let message = (error as? Failure)?.message ?? "Request failed; nothing released"
            let locked = cleanup()
            onMain {
                panel.onCancel = {}
                panel.setStatus(message, color: .systemRed)
                DispatchQueue.main.asyncAfter(deadline: .now() + resultSeconds) {
                    fail(locked ? message : message + "; lock verification failed, run `bw lock`")
                }
            }
        }
    }
}

// MARK: - Main

if CommandLine.arguments.dropFirst().first == "--clear-after" { clearLater(CommandLine.arguments) }
if CommandLine.arguments.dropFirst().first == "--serve-once" { serveOnce() }

let input = FileHandle.standardInput.readDataToEndOfFile()
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
switch (try? JSONSerialization.jsonObject(with: input) as? [String: Any])?["op"] as? String {
case "handoff": handOver(check: false); app.run()
case "handoff-check": handOver(check: true)
#if BW_BROKER_STAGING
// Staging build (own Keychain service, no touches): checks per-build items and the hand-over on the real Keychain.
case "staging-seed":
    do { try keychainSave(["v": 1, "phrase": "staging only", "sealed": [:], "vaults": [["name": "staging"]]]) } catch {
        fail("\(error)")
    }
    finish(["ok": true, "account": ownAccount])
case "staging-page":
    do { finish(["ok": true].merging(try deliverToPage("staging-value", host: "httpbin.org")) { $1 }) } catch { fail("\(error)") }
case "staging-load":
    withKeychainItem { loaded in finish(["ok": (try? loaded.get()) != nil, "account": ownAccount]) }
    app.run()
#endif
default: break
}

let request: Request
do { request = try parseRequest(input) } catch let error as Failure {
    fail(error.message)
} catch { fail("Invalid broker request") }

switch request.op {
case "status":
    let items = keychainItems()
    let own = items.first { $0.account == ownAccount }
    var status: [String: Any] = ["ok": true, "enrolled": !items.isEmpty, "vaults": (own ?? items.first)?.vaults ?? []]
    if own == nil && !items.isEmpty {
        // After an update: the previous build hands over with one touch, else macOS asks for the login password.
        status[(try? takeOver(check: true)) != nil ? "update_touch" : "keychain_prompt"] = true
    }
    finish(status)
case "forget":
    keychainDelete(all: true)
    finish(["ok": true, "enrolled": !keychainItems().isEmpty])
default:
    guard SecureEnclave.isAvailable else { fail("This Mac has no Secure Enclave / Touch ID") }
    signal(SIGTERM, SIG_IGN)  // The front end's timeout kill would skip the lock; the panel owns cleanup.
    if request.op == "enroll" { enroll(request) } else { serveRequest(request) }
    app.run()
}
