// bw-broker: the compiled core of bw-once's Touch ID path. Every security decision lives here, not in the
// editable Python front end: the request panel (personal phrase, agent's claim, checked facts), Touch ID,
// unsealing the master passwords, Bitwarden's signed CLI over a private socket, exact-host filtering, lock +
// verify, clipboard delivery. stdin: one request JSON; stdout: one result JSON (metadata only).
//
// Storage: one legacy Keychain item whose ACL trusts only this binary (another or a modified binary gets a
// visible macOS prompt), holding the phrase and a bundle of master passwords sealed to a Secure Enclave key
// that only works after Touch ID (`.biometryCurrentSet`, enforced by the enclave).
import AppKit
import CryptoKit
import Darwin
import Foundation
import LocalAuthentication
import Security

// MARK: - Basics

struct Failure: Error { let message: String }

let bitwardenRequirement =
    "anchor apple generic and identifier \"bw\" and certificate leaf[subject.OU] = \"LTZ2PFU5D6\""
let keychainService = "bw-once"
let keychainAccount = "broker"
let clipboardSeconds = 30
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
    var host = "", field = "", username: String? = nil, id: String? = nil
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
        if let id = json["id"], !(id is NSNull) {
            guard let value = (id as? String)?.lowercased(), UUID(uuidString: value) != nil else {
                throw Failure(message: "Use an exact item UUID")
            }
            request.id = value
        }
    }
    return request
}

// MARK: - Keychain (legacy file keychain: the default ACL trusts only the creating binary)

func keychainQuery() -> [String: Any] {
    [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: keychainService,
     kSecAttrAccount as String: keychainAccount, kSecUseDataProtectionKeychain as String: false]
}

/// Enrolled vault names from the item's comment attribute: no ACL prompt, no secret (also after an update).
func keychainVaults() -> [String]? {
    #if BW_BROKER_TEST
    guard let item = try? keychainLoad() else { return nil }
    return ((item["vaults"] as? [[String: String]]) ?? []).compactMap { $0["name"] }
    #endif
    var query = keychainQuery()
    query[kSecReturnAttributes as String] = true
    var result: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
          let attributes = result as? [String: Any] else { return nil }
    return ((attributes[kSecAttrComment as String] as? String) ?? "").split(separator: ",").map(String.init)
}

func keychainLoad() throws -> [String: Any]? {
    #if BW_BROKER_TEST
    guard let data = FileManager.default.contents(atPath: testEnv["BW_BROKER_TEST_STORE"]!) else { return nil }
    return try JSONSerialization.jsonObject(with: data) as? [String: Any]
    #endif
    var query = keychainQuery()
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

/// The item without any macOS dialog, or `.needsPrompt` when reading it would ask for the login password: the ACL
/// and partition list name the ad-hoc code hash of the build that created (or was "Always Allow"ed for) it, and
/// every rebuild changes that hash. `kSecUseAuthenticationUIFail` is ignored by legacy ACLs (still shows the
/// dialog, checked 2026-10-24); the old per-process switch is out of the headers but still exported.
func keychainLoadSilently() -> SilentRead {
    #if BW_BROKER_TEST
    if testEnv["BW_BROKER_TEST_KEYCHAIN_PROMPT"] == "1" { return .needsPrompt }
    #endif
    typealias Toggle = @convention(c) (DarwinBoolean) -> OSStatus
    guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "SecKeychainSetUserInteractionAllowed") else {
        return .needsPrompt  // Can't probe: explain anyway rather than risk an unexplained prompt.
    }
    let allowUI = unsafeBitCast(symbol, to: Toggle.self)
    _ = allowUI(false)
    defer { _ = allowUI(true) }
    return (try? keychainLoad()).map { .loaded($0) } ?? .needsPrompt
}

/// Runs `body` with the item. When macOS must ask first (right after a broker rebuild), a bw-once window says so
/// before the dialogs appear, so they get "Always Allow" (once per build) instead of a one-off "Allow" that
/// brings them back on every request.
func withKeychainItem(_ body: @escaping (Result<[String: Any]?, Error>) -> Void) {
    if case .loaded(let item) = keychainLoadSilently() { return body(.success(item)) }
    let built = (try? FileManager.default.attributesOfItem(atPath: here.appendingPathComponent("bw-broker").path))?[.modificationDate]
        as? Date
    let notice = Panel(title: "bw-once · macOS asks for Keychain access")
    notice.line("bw-once's broker was rebuilt" + (built.map { " on " + DateFormatter.localizedString(
        from: $0, dateStyle: .medium, timeStyle: .short) } ?? "") + " (a bw-once update). macOS now asks, up to "
        + "twice, for your Mac login password before it may open its saved item.")
    notice.line("Type it and choose Always Allow both times: until the next update, requests then need only Touch ID.",
                size: 13)
    notice.line("Not expecting a bw-once update? Choose Deny.", color: .systemOrange)
    notice.show()
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {  // Drawn before the system dialog covers it.
        let result = Result { try keychainLoad() }
        notice.window.close()
        body(result)
    }
}

func keychainSave(_ item: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: item)
    #if BW_BROKER_TEST
    try data.write(to: URL(fileURLWithPath: testEnv["BW_BROKER_TEST_STORE"]!))
    return
    #endif
    SecItemDelete(keychainQuery() as CFDictionary)
    var add = keychainQuery()
    add[kSecValueData as String] = data
    add[kSecAttrLabel as String] = "bw-once (Touch ID broker)"
    add[kSecAttrComment as String] = ((item["vaults"] as? [[String: String]]) ?? []).compactMap { $0["name"] }
        .joined(separator: ",")
    let status = SecItemAdd(add as CFDictionary, nil)
    guard status == errSecSuccess else { throw Failure(message: "Cannot save the Keychain item (\(status))") }
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

#if BW_BROKER_TEST
// Test build only (pytest compiles it with -D BW_BROKER_TEST): fake CLI, file store, fake enclave, hidden panel.
let testEnv = ProcessInfo.processInfo.environment
#endif

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

func deliver(_ secret: String) throws {
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
                ("Goes to", request.op == "copy" ? "clipboard, cleared after \(clipboardSeconds) s" : "the agent (metadata)")]
    if recopyAllowed(request) {
        rows.append(("Re-copies", "the same login's \(request.field) for this thread, \(Int(recopySeconds / 60)) min, no touch "
                     + "(each one shown)"))
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
func deliverAndOpenRecopy(_ request: Request, _ secret: String) throws -> RecopySocket? {
    guard recopyAllowed(request) else { try deliver(secret); return nil }
    let key = recopyKey(host: request.host, field: request.field, thread: request.thread ?? "")
    return try withRecopyLock(key) {
        unlink(socketPath(key))
        var socket: RecopySocket?
        if let (fd, path) = try? privateSocket(key) {
            var own = stat()
            stat(path, &own)
            socket = RecopySocket(fd: fd, path: path, inode: own.st_ino)
        }
        do { try deliver(secret) } catch {
            if let socket { close(socket.fd); unlink(socket.path) }
            throw error
        }
        return socket
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
        let delivered: Result<Void, Error>? = withRecopyLock(key) {
            guard Date() < deadline, ownsPath(socket) else { return nil }
            return Result { try deliver(secret) }
        }
        guard case .success = delivered else {
            reply(client, delivered == nil ? ["ok": false, "miss": true] : ["ok": false, "error": "Clipboard delivery failed"])
            continue
        }
        reply(client, ["ok": true, "copied": request.field, "clear_after_seconds": clipboardSeconds, "recopy": true,
                       "touch": false, "recopy_until": ISO8601DateFormatter().string(from: deadline)].merging(meta) { $1 })
        shown = Date()
        onMain {
            let notice = Panel(title: "bw-once · re-copy (no touch)")
            notice.line("Your bw-once phrase:", color: .secondaryLabelColor, size: 11)
            notice.line(phrase, size: 18, mono: true)
            notice.line("Copied \(request.field) of \(name) (\(username ?? "no username"), \(meta["vault"] as? String ?? "?")) "
                        + "again for thread \(request.thread ?? "?"). You approved this login with Touch ID; re-copies end \(until).")
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
        let recopy: RecopySocket?
        do { recopy = try deliverAndOpenRecopy(request, value) } catch {
            reply(client, ["ok": false, "error": "Clipboard delivery failed"])
            fail("Clipboard delivery failed")
        }
        var answer: [String: Any] = ["ok": true, "copied": request.field, "clear_after_seconds": clipboardSeconds]
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
                    throw Failure(message: (picked.isEmpty ? "No exact-host login matches" : "\(picked.count) logins match; pass --username or --id")
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
                    result["clear_after_seconds"] = clipboardSeconds
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
            let recopy = try secret.flatMap { try deliverAndOpenRecopy(request, $0) }
            let kept = recopy == nil ? nil : secret
            if recopy != nil { result["recopy_until"] = ISO8601DateFormatter().string(from: recopyUntil) }
            secret = nil
            onMain {
                panel.onCancel = {}
                let what = request.op == "list" ? "\((result["items"] as? [Any])?.count ?? 0) login(s) listed"
                    : "Copied \(request.field) of \(result["name"] as? String ?? "?") (\(result["username"] as? String ?? "no username"), "
                      + "\(result["vault"] as? String ?? "?"))"
                panel.setStatus("✓ \(what) · vault locked", color: .systemGreen)
                DispatchQueue.main.asyncAfter(deadline: .now() + resultSeconds) {
                    guard let recopy, let kept else { finish(result) }
                    emit(result)  // The front end returns now; this process keeps only the one released field.
                    panel.window.close()
                    var meta = result
                    ["ok", "copied", "clear_after_seconds", "recopy_until", "searched", "unavailable"].forEach { meta[$0] = nil }
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

let request: Request
do { request = try parseRequest(FileHandle.standardInput.readDataToEndOfFile()) } catch let error as Failure {
    fail(error.message)
} catch { fail("Invalid broker request") }

switch request.op {
case "status":
    let names = keychainVaults()
    var status: [String: Any] = ["ok": true, "enrolled": names != nil, "vaults": names ?? []]
    if names != nil, case .needsPrompt = keychainLoadSilently() { status["keychain_prompt"] = true }
    finish(status)
case "forget":
    SecItemDelete(keychainQuery() as CFDictionary)
    finish(["ok": true, "enrolled": false])
default:
    guard SecureEnclave.isAvailable else { fail("This Mac has no Secure Enclave / Touch ID") }
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    signal(SIGTERM, SIG_IGN)  // The front end's timeout kill would skip the lock; the panel owns cleanup.
    if request.op == "enroll" { enroll(request) } else { serveRequest(request) }
    app.run()
}
