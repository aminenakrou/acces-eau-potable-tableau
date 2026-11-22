"""Recalcule les chiffres clés du tableau de bord à partir des CSV bruts.

Le but est de contrôler les résultats affichés dans Tableau avec un calcul
indépendant, en reproduisant le même modèle de données :
  - jointure gauche Eau + Population sur (Pays, Année, Zone) ;
  - « China » (OMS) relié à « China, mainland » (FAO), sans l'agrégat FAO ;
  - taux d'accès pondérés par la population.

Utilisation :
    pip install -r requirements.txt
    python scripts/verifier_chiffres.py
"""

import sys
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


def lire(nom: str) -> pd.DataFrame:
    return pd.read_csv(DATA / nom, encoding="utf-8-sig")


def charger() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    eau = lire("BasicAndSafelyManagedDrinkingWaterServices.csv")
    eau.columns = ["annee", "pays", "zone", "basique", "securise"]

    pop = lire("Population.csv").rename(
        columns={"Country": "pays", "Granularity": "zone", "Year": "annee", "Population": "pop_milliers"}
    )
    # Harmonisation des noms de pays FAO -> OMS
    pop = pop[pop["pays"] != "China"]  # agrégat avec Hong Kong, Macao, Taïwan
    pop["pays"] = pop["pays"].replace(
        {"China, mainland": "China", "North Macedonia": "Republic of North Macedonia"}
    )

    regions = lire("RegionCountry.csv")
    regions.columns = ["region", "pays"]

    df = eau.merge(pop, on=["pays", "annee", "zone"], how="left").merge(regions, on="pays", how="left")
    assert len(df) == len(eau), "la jointure ne doit pas créer de doublons"
    df["pop"] = df["pop_milliers"] * 1000
    df["sans_acces"] = (1 - df["basique"] / 100) * df["pop"]

    stab = lire("PoliticalStability.csv").rename(
        columns={"Country": "pays", "Year": "annee", "Political_Stability": "stabilite"}
    )
    stab["pays"] = stab["pays"].replace(
        {"China, mainland": "China", "North Macedonia": "Republic of North Macedonia"}
    )

    mort = lire("MortalityRateAttributedToWater.csv")
    mort.columns = ["annee", "pays", "sexe", "mortalite", "deces"]
    mort = mort[mort["sexe"] == "Total"]
    return df, stab, mort


def taux_pondere(d: pd.DataFrame, col: str) -> float:
    d = d[d[col].notna() & d["pop"].notna()]
    return (d[col] * d["pop"]).sum() / d["pop"].sum()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # accents corrects dans la console Windows
    df, stab, mort = charger()
    total = df[df["zone"] == "Total"]

    print("== Monde ==")
    for annee in (2000, 2017):
        t = total[total["annee"] == annee]
        print(
            f"{annee} : accès basique {taux_pondere(t, 'basique'):.1f} % | "
            f"accès sécurisé {taux_pondere(t, 'securise'):.1f} % | "
            f"sans accès basique {t['sans_acces'].sum() / 1e6:.0f} M"
        )
    print(f"Décès WASH (2016) : {mort['deces'].sum():,.0f}".replace(",", " "))

    t17 = total[total["annee"] == 2017]
    print("\n== Personnes sans accès basique par région, 2017 (millions) ==")
    print((t17.groupby("region")["sans_acces"].sum() / 1e6).round(0).sort_values(ascending=False).to_string())

    afr = t17[t17["region"] == "Africa"]
    print(
        f"\nAfrique 2017 : accès basique {taux_pondere(afr, 'basique'):.1f} % | "
        f"accès sécurisé {taux_pondere(afr, 'securise'):.1f} % | "
        f"part du total mondial sans accès {afr['sans_acces'].sum() / t17['sans_acces'].sum():.0%}"
    )

    print("\n== Ville / campagne, 2017 (accès basique, %) ==")
    zones = df[(df["annee"] == 2017) & df["zone"].isin(["Rural", "Urban"])]
    zones = zones.pivot_table(index="pays", columns="zone", values="basique")
    print(zones.loc[["Democratic Republic of the Congo", "Angola", "Chad"]].round(1).to_string())

    print("\n== Niger ==")
    niger = df[df["pays"] == "Niger"].set_index(["annee", "zone"])
    for annee in (2000, 2017):
        n = niger.loc[annee]
        print(
            f"{annee} : population {n.loc['Total', 'pop'] / 1e6:.1f} M | "
            f"accès basique {n.loc['Total', 'basique']:.1f} % (rural {n.loc['Rural', 'basique']:.1f} %) | "
            f"part rurale {n.loc['Rural', 'pop'] / n.loc['Total', 'pop']:.0%}"
        )

    print("\n== Domaine 3 : score d'efficacité (2016) ==")
    b16 = total[total["annee"] == 2016].set_index("pays")["basique"]
    m = mort.set_index("pays")["mortalite"]
    score = (0.5 * b16 + 50 * (1 - m / m.max())).dropna()
    s16 = stab[stab["annee"] == 2016].set_index("pays")["stabilite"]
    for pays in ("Benin", "Zambia", "Comoros", "Chad", "Niger"):
        print(f"{pays:8s} score {score[pays]:.0f}/100 | stabilité {s16[pays]:+.2f}")


if __name__ == "__main__":
    main()
