import AppKit
import Darwin

let board = NSPasteboard.general
let owner = NSPasteboard.PasteboardType("org.bw-once.owner")
if CommandLine.arguments.dropFirst().first == "--clear-if-ours" {
    // Reads only the item's type list, never its value; a newer unrelated copy stays untouched.
    if board.types?.contains(owner) == true {
        board.clearContents()
        print("cleared")
    } else {
        print("not-ours")
    }
    exit(0)
}
let content = FileHandle.standardInput.readDataToEndOfFile()
guard let secret = String(data: content, encoding: .utf8), !secret.isEmpty else { exit(1) }
let item = NSPasteboardItem()
let token = UUID().uuidString
item.setString(secret, forType: .string)
item.setString(token, forType: owner)
item.setData(Data(), forType: NSPasteboard.PasteboardType("org.nspasteboard.ConcealedType"))
item.setData(Data(), forType: NSPasteboard.PasteboardType("org.nspasteboard.TransientType"))
board.clearContents()
guard board.writeObjects([item]) else { exit(1) }
let count = board.changeCount
print("ready")
fflush(stdout)
Thread.sleep(forTimeInterval: 30)
if board.changeCount == count && board.string(forType: owner) == token {
    board.clearContents()
}
