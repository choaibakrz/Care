// La lecture de texte déjà présente dans le Mac (cadre « Vision » d'Apple), pour lire un papier depuis une image.
// Clinique en boîte, tâche R3 (autorisation B de Hiba). Tout se passe sur l'ordinateur : rien n'est envoyé ailleurs.
//
//   lecture_mac lire IMAGE.png                 → une ligne JSON : {"lignes": […], "sans_correction": […]}
//                                                (chaque ligne : texte, confiance, x, y, hauteur)
//   lecture_mac dessiner TEXTE.txt IMAGE.png [POLICE] [TAILLE] [MOT EN TRAVERS]
//                                              → fabrique une image d'essai : le texte, noir sur blanc
//
// Compilé une fois par briques/clinique/lecture_mac.py (swiftc, déjà sur le Mac avec Xcode). Rien n'est installé.
import AppKit
import Foundation
import Vision

// Une passe de lecture. Avec la correction (les mots sont corrigés d'après la langue) ou sans (les lettres telles que vues).
func passe(_ cg: CGImage, correction: Bool) -> [[String: Any]]? {
    let requete = VNRecognizeTextRequest()
    requete.recognitionLevel = .accurate
    requete.usesLanguageCorrection = correction
    requete.recognitionLanguages = ["fr-FR", "de-DE", "it-IT", "en-US"]
    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([requete])
    } catch {
        fputs("lecture impossible : \(error)\n", stderr)
        return nil
    }
    var lignes: [[String: Any]] = []
    for observation in requete.results ?? [] {
        if let candidat = observation.topCandidates(1).first {
            let cadre = observation.boundingBox  // origine en bas à gauche, de 0 à 1
            lignes.append(["texte": candidat.string, "confiance": Double(candidat.confidence),
                           "x": Double(cadre.minX), "y": Double(cadre.minY), "hauteur": Double(cadre.height)])
        }
    }
    lignes.sort { ($0["y"] as! Double) > ($1["y"] as! Double) }  // de haut en bas
    return lignes
}

// Deux passes : avec la correction (le meilleur texte), et sans (la confiance qu'elle annonce alors est plus franche :
// avec la correction, la confiance vaut presque toujours 1, même quand la lecture se trompe ; mesuré le 12.11.2026).
func lire(_ chemin: String) -> Int32 {
    guard let image = NSImage(contentsOfFile: chemin),
          let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        fputs("image illisible : \(chemin)\n", stderr)
        return 2
    }
    guard let corrigees = passe(cg, correction: true), let brutes = passe(cg, correction: false) else { return 3 }
    guard let donnees = try? JSONSerialization.data(withJSONObject: ["lignes": corrigees, "sans_correction": brutes], options: []),
          let texte = String(data: donnees, encoding: .utf8) else { return 3 }
    print(texte)
    return 0
}

func dessiner(_ fichierTexte: String, _ sortie: String, police nomPolice: String, taille: CGFloat, travers: String) -> Int32 {
    guard let texte = try? String(contentsOfFile: fichierTexte, encoding: .utf8) else {
        fputs("texte illisible : \(fichierTexte)\n", stderr)
        return 2
    }
    guard let police = NSFont(name: nomPolice, size: taille) else {
        fputs("police absente de ce Mac : \(nomPolice)\n", stderr)
        return 4
    }
    let ecrit = NSAttributedString(string: texte, attributes: [.font: police, .foregroundColor: NSColor.black])
    let marge: CGFloat = 50
    let largeur: CGFloat = 1240
    let cadre = ecrit.boundingRect(with: NSSize(width: largeur - 2 * marge, height: 20000), options: [.usesLineFragmentOrigin])
    // une page, pas une bandelette : au moins 900 points de haut (le mot en travers tient alors sur la page)
    let hauteur = max(ceil(cadre.height) + 2 * marge, 900)
    guard let image = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(largeur), pixelsHigh: Int(hauteur),
                                       bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                       colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return 3 }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: image)
    NSColor.white.setFill()
    NSRect(x: 0, y: 0, width: largeur, height: hauteur).fill()
    ecrit.draw(with: NSRect(x: marge, y: marge, width: largeur - 2 * marge, height: hauteur - 2 * marge),
               options: [.usesLineFragmentOrigin])
    if !travers.isEmpty {  // un mot écrit en travers, en gris clair (« INVENTÉ ») : il fait partie de l'image
        let grand = NSFont(name: "Helvetica-Bold", size: 110) ?? NSFont.boldSystemFont(ofSize: 110)
        let mot = NSAttributedString(string: travers, attributes: [.font: grand, .foregroundColor: NSColor(white: 0.55, alpha: 0.35)])
        let dimension = mot.size()
        let transformation = NSAffineTransform()
        transformation.translateX(by: largeur / 2, yBy: hauteur / 2)
        transformation.rotate(byDegrees: 24)
        transformation.concat()
        mot.draw(at: NSPoint(x: -dimension.width / 2, y: -dimension.height / 2))
    }
    NSGraphicsContext.restoreGraphicsState()
    guard let png = image.representation(using: .png, properties: [:]) else { return 3 }
    do { try png.write(to: URL(fileURLWithPath: sortie)) } catch { return 3 }
    return 0
}

let arguments = CommandLine.arguments
if arguments.count == 3 && arguments[1] == "lire" {
    exit(lire(arguments[2]))
} else if arguments.count >= 4 && arguments[1] == "dessiner" {
    // facultatif, dans cet ordre : la police, sa taille, le mot à écrire en travers
    let nomPolice = arguments.count > 4 ? arguments[4] : "Helvetica"
    let taille = arguments.count > 5 ? CGFloat(Double(arguments[5]) ?? 30) : 30
    let travers = arguments.count > 6 ? arguments[6] : ""
    exit(dessiner(arguments[2], arguments[3], police: nomPolice, taille: taille, travers: travers))
} else {
    fputs("usage : lecture_mac lire IMAGE | lecture_mac dessiner TEXTE.txt IMAGE.png [POLICE] [TAILLE] [MOT EN TRAVERS]\n", stderr)
    exit(64)
}
