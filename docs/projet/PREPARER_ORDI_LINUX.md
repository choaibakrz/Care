# Préparer l'ordinateur Linux pour le bras — feuille pour le collaborateur

*Écrit dans la nuit du 14 au 15.11.2026. Rien de cette feuille n'a été essayé sur le vrai bras.
Les commandes viennent de la documentation publique du fabricant du bras (AgileX, kit `piper_sdk`, licence MIT),
lue le 14.11.2026. Ubuntu 22.04 est une des versions qu'il dit avoir testées.*

## Le but

Le cerveau du projet tourne sur le MacBook de Hiba. Le kit du bras ne marche que sous Linux. Ton ordinateur sera
donc **le relais du bras** : il est branché au bras, il reçoit quelques ordres simples du MacBook, et il les passe au bras.
Tous les ordres restent vérifiés par le gardien, sur le MacBook, avant d'arriver chez toi.

## Les règles de sécurité, avant tout

- **On ne met pas le courant dans le bras sans la personne qui a fait son câblage.** Il a été monté à la main, avec un
  convertisseur de tension. Le fabricant écrit : pas plus de 26 volts, au moins 10 ampères.
- Le bras reste fixé par ses deux serre-joints. Personne n'a le corps ni la tête dans la zone qu'il peut atteindre.
- **Ne lance aucun exemple du fabricant tel quel.** Presque tous mettent les moteurs sous tension dès le début, et un
  exemple dont le nom dit « read » coupe la détection des chocs.
- L'arrêt « rapide » du kit fait **descendre** le bras. Sa remise à zéro le fait **tomber**. On ne les appelle pas.
- Aucun ordre de mouvement tant que Hiba n'a pas dit oui et que les arrêts ne sont pas choisis.

## Étape 1 — Installer (bras éteint, rien de branché)

C'est ton ordinateur : c'est toi qui décides d'installer. Tout va dans un espace à part (`~/bras_env`).

```bash
sudo apt update && sudo apt install can-utils ethtool python3-venv
```

```bash
python3 -m venv ~/bras_env && source ~/bras_env/bin/activate
```

```bash
pip3 install python-can piper_sdk
```

Note ici la version installée : `pip3 show piper_sdk` → version ______________

## Étape 2 — Brancher le boîtier USB du bras (bras toujours éteint)

Le boîtier du bras est la petite pièce noire marquée « USB CAN H L », au bout du câble gris. **Pas** le boîtier bleu
« Mini CANFD-I » : celui-là est pour la main.

Branche la prise USB dans ton ordinateur, puis regarde si Linux le voit :

```bash
ip link show | grep -i can
```

Tu dois voir une ligne `can0`. Sinon : `dmesg | tail -20` et envoie-nous ce qui s'affiche.

Puis mets le câble de données en route, au débit du bras (commande installée avec le kit) :

```bash
piper-can activate can0 1000000
```

## Étape 3 — Écouter le bras (feu orange : il faut le courant)

Cette étape demande d'allumer le bras. Donc : la personne qui a fait le câblage est là, Hiba a dit oui, la zone est
vide, quelqu'un a la main sur la prise.

Pour écouter sans rien envoyer du tout :

```bash
candump can0
```

- Des lignes défilent : le bras parle, tout va bien. Arrête avec Ctrl+C.
- Rien ne s'affiche : le bras ne parle pas. Les deux fils de données (jaune et bleu) sont peut-être inversés sur le
  petit bornier vert, ou le bras est en mode « bras maître ». On ne touche à rien d'autre, on en parle.

`candump` ne fait qu'écouter : il n'envoie rien, il ne met aucun moteur sous tension.

## Étape 4 — Le réseau entre les deux ordinateurs

- Les deux ordinateurs se mettent sur **le partage de connexion d'un téléphone de l'équipe**. Pas le Wi-Fi de la salle :
  le relais n'a pas de mot de passe, n'importe qui pourrait lui parler.
- Note l'adresse de ton ordinateur sur ce réseau : `hostname -I` → ______________

## Ce qui vient ensuite (préparé par Hiba et son agent)

Un petit programme, « le relais », à lancer sur ton ordinateur. Il n'acceptera que quelques ordres : dire l'état du
bras, s'arrêter, jouer **un seul** geste lent appris à la main. Il sera d'abord essayé sur un faux bras.

## Ce qu'il faut nous dire

1. La version de `piper_sdk` installée.
2. Ce que montre `ip link show | grep -i can`.
3. Ce que montre `candump can0` quand le bras est allumé (dix lignes suffisent).
4. Ce qui est écrit sur l'étiquette à code QR, sur la base du bras (modèle, version).
