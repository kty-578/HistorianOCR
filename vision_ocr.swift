import AppKit
import Foundation
import Vision

struct OCRWord: Encodable {
    let text: String
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct OCRLine: Encodable {
    let text: String
    let confidence: Float
    let x: Double
    let y: Double
    let width: Double
    let height: Double
    let words: [OCRWord]
}

guard CommandLine.arguments.count == 2 else {
    fputs("Usage: vision_ocr IMAGE\n", stderr)
    exit(2)
}

let path = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: path),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    fputs("Could not read image\n", stderr)
    exit(2)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["fr-FR"]
request.usesLanguageCorrection = false

let handler = VNImageRequestHandler(cgImage: cgImage)
try handler.perform([request])

let observations = (request.results ?? []).sorted {
    if abs($0.boundingBox.midY - $1.boundingBox.midY) > 0.008 {
        return $0.boundingBox.midY > $1.boundingBox.midY
    }
    return $0.boundingBox.minX < $1.boundingBox.minX
}

let lines: [OCRLine] = observations.compactMap { observation in
    guard let candidate = observation.topCandidates(1).first else { return nil }
    let box = observation.boundingBox
    let expression = try! NSRegularExpression(pattern: "\\S+")
    let words: [OCRWord] = expression.matches(in: candidate.string, range: NSRange(candidate.string.startIndex..., in: candidate.string)).compactMap { match in
        guard let range = Range(match.range, in: candidate.string),
              let rectangle = try? candidate.boundingBox(for: range) else { return nil }
        let bounds = rectangle.boundingBox
        return OCRWord(text: String(candidate.string[range]), x: bounds.minX,
                       y: bounds.minY, width: bounds.width, height: bounds.height)
    }
    return OCRLine(
        text: candidate.string,
        confidence: candidate.confidence,
        x: box.minX,
        y: box.minY,
        width: box.width,
        height: box.height,
        words: words
    )
}

let data = try JSONEncoder().encode(lines)
FileHandle.standardOutput.write(data)
