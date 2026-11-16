// H19 — Lire un code QR dans une image PNG, avec CoreImage (la bibliothèque d'images d'Apple, déjà sur le Mac).
// Sert à vérifier les codes QR dessinés par segno, sans faire confiance à segno : `swift outils/lire_code_qr.swift image.png`
// Écrit le texte de chaque code QR trouvé, un par ligne. Rien n'est envoyé sur le réseau.
import CoreImage
import Foundation
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let image = CIImage(contentsOf: url) else { print("IMAGE ILLISIBLE"); exit(2) }
let detecteur = CIDetector(ofType: CIDetectorTypeQRCode, context: nil, options: [CIDetectorAccuracy: CIDetectorAccuracyHigh])
for f in detecteur?.features(in: image) ?? [] { if let q = f as? CIQRCodeFeature { print(q.messageString ?? "") } }
