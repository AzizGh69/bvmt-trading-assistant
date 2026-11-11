# Base de connaissances de l'assistant

Ce fichier est découpé en sections (un titre `##` par section). L'assistant
retrouve les sections les plus proches de la question et s'appuie dessus. Il
décrit ce que fait l'application et les notions qu'elle utilise ; il ne contient
aucune donnée de marché, celles-ci viennent de l'historique des cours.

## La Bourse de Tunis (BVMT)

La Bourse des Valeurs Mobilières de Tunis (BVMT) est le marché boursier tunisien.
Les cours y sont exprimés en dinars tunisiens (TND). Le marché est supervisé par
le Conseil du Marché Financier (CMF), l'autorité de régulation. Les sociétés
cotées appartiennent surtout aux secteurs des banques, des assurances, du
leasing, de l'agroalimentaire, de l'industrie et de la distribution. Beaucoup
de titres sont peu liquides : ils ne s'échangent pas à toutes les séances, ce
qui rend les statistiques plus fragiles que sur un grand marché.

## L'indice TUNINDEX et l'indice affiché par l'application

Le TUNINDEX est l'indice de référence de la BVMT, pondéré par les
capitalisations flottantes, base 1000 au 31 décembre 1997. L'application n'a pas
les valeurs officielles de l'indice : elle affiche un indice composite calculé à
partir de ses propres cours, pondéré par la liquidité (les capitaux échangés).
C'est une approximation qui suit la même direction générale que le TUNINDEX mais
ne lui est pas identique.

## Les données de l'application

L'historique couvre les séances de 2016 au 6 février 2026 : 89 valeurs, dont 77
encore cotées à la dernière séance. Pour chaque séance et chaque valeur : cours
d'ouverture, plus haut, plus bas, clôture, volume, nombre de transactions et
capitaux. Une valeur qui ne s'est pas échangée garde son dernier cours. Les
variations de plus de 15 % en une séance sont traitées comme des opérations sur
titres (division, attribution gratuite) et écartées des calculs de rendement.

## Les indicateurs techniques : RSI, MACD, bandes de Bollinger

Le RSI (Relative Strength Index, 14 séances) varie de 0 à 100 ; sous 30 un titre
est dit survendu, au-dessus de 70 suracheté. La MACD est l'écart entre deux
moyennes exponentielles (12 et 26 séances) ; son histogramme compare la MACD à
sa propre moyenne sur 9 séances. Les bandes de Bollinger entourent la moyenne de
20 séances à deux écarts-types ; une clôture hors des bandes est inhabituelle.
Ces indicateurs décrivent le passé récent ; ils ne prédisent pas à eux seuls.

## Comment les prévisions sont faites

Pour chaque valeur, trois modèles prédisent les 5 prochaines séances : un ARIMA
(ordre choisi par le critère AIC, le BIC est aussi affiché), une moyenne
exponentielle amortie et la marche aléatoire (le dernier cours reste le même).
Ils sont comparés sur un backtest glissant des 120 dernières séances : celui qui
a la plus petite erreur (RMSE) est retenu. Le test ADF indique si la série est
stationnaire. Les intervalles à 80 % et 95 % donnent l'incertitude. Quand aucun
modèle ne bat la marche aléatoire, l'application le dit : sur la plupart des
valeurs, prédire le cours de demain mieux que « le même qu'aujourd'hui » est
difficile.

## La détection d'anomalies (surveillance)

Une séance est signalée quand le volume dépasse de plus de 3 écarts-types la
moyenne des 60 séances précédentes, quand le cours varie de plus de 5 %, ou
quand une forêt d'isolement (Isolation Forest) la juge atypique sur trois
mesures : volume, ampleur du mouvement et écart haut-bas. Les variations de plus
de 15 % sont classées « opération sur titres » à faible gravité. La gravité
(faible, moyenne, élevée, critique) cumule les signaux. Une anomalie n'est pas
une preuve de manipulation : c'est une séance à regarder.

## Le portefeuille recommandé (Markowitz)

L'allocation est une optimisation moyenne-variance de Markowitz, sans vente à
découvert, sur les 40 valeurs cotées les plus liquides des 500 dernières
séances. La covariance est estimée avec la méthode de Ledoit-Wolf et les
rendements moyens sont tirés à 70 % vers la moyenne du marché, parce que les
moyennes historiques sont très bruitées. Trois profils : prudent (aversion au
risque 12, 15 % au plus par valeur), équilibré (5 et 25 %), dynamique (2 et
35 %). Chaque ligne est expliquée par sa part du rendement attendu et sa part du
risque (décomposition d'Euler).

## Le test hors échantillon : ce que vaut vraiment l'optimisation

Les chiffres calculés sur la période qui a servi à choisir les poids sont
flatteurs par construction. L'application refait donc le choix sur la première
moitié de l'historique et le mesure sur la seconde, qu'il n'a jamais vue, à côté
d'un portefeuille à parts égales. Sur les données actuelles, le portefeuille
optimisé fait moins bien que les parts égales hors échantillon. Il faut lire
l'allocation comme un exercice de diversification et de mesure du risque, pas
comme une promesse de performance.

## Les mesures de risque : volatilité, Sharpe, perte maximale, VaR, CVaR

La volatilité est l'écart-type annualisé des rendements quotidiens. Le ratio de
Sharpe divise le rendement en excès du taux sans risque (7 % par an ici, proche
du taux du marché monétaire tunisien) par la volatilité. La perte maximale est
la plus forte baisse entre un sommet et un creux. La VaR à 95 % est la perte
d'une séance qui n'est dépassée qu'une séance sur vingt ; la CVaR est la perte
moyenne au-delà. Les tests de résistance rejouent les pires 20 séances et la
pire séance de l'indice, et supposent un marché à −10 % et un premier secteur à
−15 %.

## Le portefeuille simulé

Chaque compte dispose d'un portefeuille fictif (10 000 TND par défaut). Les
ordres s'exécutent au dernier cours de clôture connu, sans frais, sans carnet
d'ordres et sans exécution partielle. « Suivre l'allocation recommandée » vend
d'abord ce qui dépasse la cible puis achète ce qui manque. On peut repartir de
zéro à tout moment. Aucun ordre réel n'est jamais passé.

## Les agents et le moteur de décision

Cinq agents analysent une valeur à tour de rôle : marché (cours, liquidité,
indicateurs), prévision, sentiment (actualités), anomalies, puis recommandation.
Chaque passage de relais est enregistré. Le moteur pèse trois signaux
directionnels (prévision 40 %, technique 35 %, actualités 25 %) ; la prévision
ne compte que si son modèle bat la marche aléatoire. Le score est comparé à un
seuil qui dépend du profil (0,35 prudent, 0,25 équilibré, 0,15 dynamique). Des
règles de sécurité peuvent ensuite bloquer un achat : valeur plus cotée,
séance inhabituelle grave récente, valeur peu liquide, trop peu de signaux,
ligne déjà au plafond du profil ; et sans position, « vendre » devient
« éviter ».

## Apprendre de vos avis

Après une recommandation d'achat ou de vente, un pouce levé ou baissé ajuste,
pour vous seulement, la confiance accordée à chaque signal (entre 0,5 et 1,5).
Un signal qui allait dans le sens d'une recommandation appréciée gagne du poids,
un signal qui allait dans le sens d'une recommandation rejetée en perd. Les
recommandations « conserver » n'apprennent rien. Les règles de sécurité ne
changent jamais.

## Le sentiment des actualités

Avec une clé de modèle de langage configurée, le modèle note chaque texte de −1
à +1. Sinon, un lexique français, arabe et tunizi le fait : les chiffres de
l'arabizi sont lus comme des lettres (3 pour ع, 7 pour ح, 9 pour ق), une
négation inverse le mot qui suit (« ma tla3ch »), et les expressions sont lues
en entier (« baisse des bénéfices »). La lecture des flux d'actualités est
désactivée par défaut ; sans elle, le signal « actualités » est absent.

## Les limites de l'application

C'est un projet éducatif. Les données s'arrêtent au 6 février 2026 et ne sont pas
mises à jour en direct. Les prévisions et les recommandations sont des calculs
statistiques sur le passé, avec leurs incertitudes ; elles ne sont pas des
conseils en investissement. Avant toute décision réelle, consultez un
intermédiaire en bourse agréé.
