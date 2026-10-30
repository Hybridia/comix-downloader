import Foundation
// Usage: icloud-status <file>... — one line per file:
//   uploaded<TAB>path | uploading<TAB>path<TAB>doneBytes<TAB>totalBytes | waiting<TAB>path
//   error<TAB>path<TAB>reason | not_icloud<TAB>path | missing<TAB>path
// A file being uploaded can still carry the error of an earlier failed
// attempt, so "uploading" wins over the error flag. Byte progress comes
// from the same per-file NSProgress Finder shows ("22,5 MB of 228,7 MB").
let keys: Set<URLResourceKey> = [.isUbiquitousItemKey, .ubiquitousItemIsUploadedKey,
                                 .ubiquitousItemIsUploadingKey, .ubiquitousItemUploadingErrorKey]
var lines: [String] = []
var uploading: [(Int, URL)] = []
for path in CommandLine.arguments.dropFirst() {
    guard FileManager.default.fileExists(atPath: path) else { lines.append("missing\t\(path)"); continue }
    let url = URL(fileURLWithPath: path)
    guard let v = try? url.resourceValues(forKeys: keys) else { lines.append("waiting\t\(path)"); continue }
    if !(v.isUbiquitousItem ?? false) { lines.append("not_icloud\t\(path)") }
    else if v.ubiquitousItemIsUploaded ?? false { lines.append("uploaded\t\(path)") }
    else if v.ubiquitousItemIsUploading ?? false { uploading.append((lines.count, url)); lines.append("uploading\t\(path)") }
    else if let e = v.ubiquitousItemUploadingError { lines.append("error\t\(path)\t\(e.localizedDescription)") }
    else { lines.append("waiting\t\(path)") }
}
if !uploading.isEmpty {
    var done: [Int: (Int64, Int64)] = [:]
    var subs: [Any] = []
    for (i, url) in uploading {
        subs.append(Progress.addSubscriber(forFileURL: url) { p in
            done[i] = (p.completedUnitCount, p.totalUnitCount)
            return {}
        })
    }
    let end = Date().addingTimeInterval(0.8)
    while done.count < uploading.count && Date() < end { RunLoop.main.run(until: Date().addingTimeInterval(0.05)) }
    for s in subs { Progress.removeSubscriber(s) }
    for (i, _) in uploading { if let (c, t) = done[i] { lines[i] += "\t\(c)\t\(t)" } }
}
print(lines.joined(separator: "\n"))
