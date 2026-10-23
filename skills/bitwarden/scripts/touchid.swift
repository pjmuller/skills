// Seals one secret to a Secure Enclave key that only this Mac's enclave can use, and only after Touch ID:
// `.biometryCurrentSet` is enforced by the enclave itself (no entitlement or signing identity needed), and new
// or removed fingerprints invalidate the key. bw-once keeps the sealed JSON; this helper never touches files.
//   touchid seal CONTEXT        stdin secret → stdout sealed JSON (no prompt)
//   touchid open CONTEXT REASON stdin sealed JSON → Touch ID dialog showing REASON → stdout secret
import CryptoKit
import Foundation
import LocalAuthentication

func fail(_ message: String, _ code: Int32) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(code)
}

func symmetricKey(_ shared: SharedSecret, _ ephemeral: P256.KeyAgreement.PublicKey, _ context: String) -> SymmetricKey {
    shared.hkdfDerivedSymmetricKey(using: SHA256.self, salt: ephemeral.x963Representation,
                                   sharedInfo: Data(context.utf8), outputByteCount: 32)
}

let args = CommandLine.arguments
guard args.count >= 3, SecureEnclave.isAvailable else { fail("usage: touchid seal|open CONTEXT [REASON]", 2) }
let context = "bw-once touchid v1 " + args[2]
let input = FileHandle.standardInput.readDataToEndOfFile()

switch args[1] {
case "seal" where args.count == 3:
    guard !input.isEmpty, let access = SecAccessControlCreateWithFlags(
        nil, kSecAttrAccessibleWhenUnlockedThisDeviceOnly, [.privateKeyUsage, .biometryCurrentSet], nil) else {
        fail("nothing to seal", 2)
    }
    do {
        let key = try SecureEnclave.P256.KeyAgreement.PrivateKey(accessControl: access)
        let ephemeral = P256.KeyAgreement.PrivateKey()  // Public-key encryption: sealing needs no Touch ID.
        let shared = try ephemeral.sharedSecretFromKeyAgreement(with: key.publicKey)
        let box = try AES.GCM.seal(input, using: symmetricKey(shared, ephemeral.publicKey, context))
        let sealed = ["v": "1", "key": key.dataRepresentation.base64EncodedString(),
                      "ephemeral": ephemeral.publicKey.x963Representation.base64EncodedString(),
                      "box": box.combined!.base64EncodedString()]
        FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: sealed))
    } catch {
        fail("seal failed", 1)
    }
case "open" where args.count == 4:
    guard let sealed = try? JSONSerialization.jsonObject(with: input) as? [String: String], sealed["v"] == "1",
          let keyData = Data(base64Encoded: sealed["key"] ?? ""),
          let ephemeralData = Data(base64Encoded: sealed["ephemeral"] ?? ""),
          let boxData = Data(base64Encoded: sealed["box"] ?? "") else { fail("invalid sealed secret", 2) }
    let auth = LAContext()
    auth.localizedReason = args[3]
    auth.localizedFallbackTitle = ""  // No password fallback in the dialog: finger or cancel.
    do {
        let key = try SecureEnclave.P256.KeyAgreement.PrivateKey(dataRepresentation: keyData, authenticationContext: auth)
        let ephemeral = try P256.KeyAgreement.PublicKey(x963Representation: ephemeralData)
        let shared = try key.sharedSecretFromKeyAgreement(with: ephemeral)  // Touch ID dialog happens here.
        let secret = try AES.GCM.open(AES.GCM.SealedBox(combined: boxData), using: symmetricKey(shared, ephemeral, context))
        FileHandle.standardOutput.write(secret)
    } catch let error as LAError where [.userCancel, .systemCancel, .appCancel, .userFallback].contains(error.code) {
        fail("cancelled", 3)
    } catch {
        fail("Touch ID unlock failed (fingerprints changed or enrolment invalid?)", 1)
    }
default:
    fail("usage: touchid seal|open CONTEXT [REASON]", 2)
}
