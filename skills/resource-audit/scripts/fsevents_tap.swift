// Read-only FSEvents tap: counts file events per path prefix (no root needed).
// Usage: swiftc -O -o /tmp/fsevents_tap fsevents_tap.swift && /tmp/fsevents_tap 20
// Shows which trees churn when fseventsd/Spotlight burn CPU or memory.
import Foundation
import CoreServices
let secs = Double(CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "20")!
var counts = [String: Int](); var total = 0; var dropped = 0
let cb: FSEventStreamCallback = { _, _, n, paths, flags, _ in
  let ps = unsafeBitCast(paths, to: NSArray.self) as! [String]
  for i in 0..<n {
    let f = flags[i]
    if f & UInt32(kFSEventStreamEventFlagUserDropped | kFSEventStreamEventFlagKernelDropped | kFSEventStreamEventFlagMustScanSubDirs) != 0 { dropped += 1 }
    let comps = ps[i].split(separator: "/", omittingEmptySubsequences: true).prefix(5)
    counts["/" + comps.joined(separator: "/"), default: 0] += 1; total += 1
  }
}
let stream = FSEventStreamCreate(nil, cb, nil, ["/"] as CFArray, FSEventStreamEventId(kFSEventStreamEventIdSinceNow), 0.5,
  FSEventStreamCreateFlags(kFSEventStreamCreateFlagFileEvents | kFSEventStreamCreateFlagNoDefer | kFSEventStreamCreateFlagUseCFTypes))!
FSEventStreamSetDispatchQueue(stream, DispatchQueue.main)
FSEventStreamStart(stream)
DispatchQueue.main.asyncAfter(deadline: .now() + secs) {
  print("total \(total) dropped/rescan-flags \(dropped) in \(secs)s")
  for (k, v) in counts.sorted(by: { $0.value > $1.value }).prefix(30) { print(String(format: "%8d  ", v) + k) }
  exit(0)
}
dispatchMain()
