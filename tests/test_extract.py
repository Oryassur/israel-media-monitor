"""extract_items: promo links on commerce subdomains are not headlines."""
import unittest

from pipeline.extract import extract_items

PAGE = """<html><body><main>
<a href="https://abonnement.lefigaro.fr/abonnement-premium-figaro-vente-flash?app=Figaro">VENTE FLASH -70% par mois pendant 12 mois</a>
<a href="https://www.lefigaro.fr/international/un-vrai-titre-assez-long-pour-passer-20260911">Un vrai titre d'article assez long pour passer le filtre</a>
<a href="https://boutique.lefigaro.fr/offre">Une offre de la boutique avec un texte assez long</a>
<a href="https://sport.lefigaro.fr/football/un-titre-sportif-assez-long">Un titre sportif sur le sous-domaine sport, gardé</a>
</main></body></html>"""


class TestSkipHosts(unittest.TestCase):
    def test_commerce_subdomains_skipped(self):
        got = [it["url"] for it in extract_items(PAGE, "https://www.lefigaro.fr", "main")]
        self.assertEqual(got, [
            "https://www.lefigaro.fr/international/un-vrai-titre-assez-long-pour-passer-20260911",
            "https://sport.lefigaro.fr/football/un-titre-sportif-assez-long",
        ])


if __name__ == "__main__":
    unittest.main()
