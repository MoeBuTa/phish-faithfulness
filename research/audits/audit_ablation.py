"""What IS the 0.899 residual, after size-matching?

The earlier claim -- "it is a brand-name lexical prior" -- was read off logistic-regression
coefficients and never tested. Codex ran the ablation and the accuracy barely moved, which
refutes it. This script redoes that ablation with a PUBLIC-SUFFIX-AWARE alias set (the
earlier reg() returned 'co.jp' for rakuten.co.jp and handed eight brands the alias 'com')
and then keeps ablating, to find out what the signal actually is.

Ladder:
  A0  full visible text                              (the 0.899 baseline)
  A1  minus every brand alias                        (tests the brand-prior claim)
  A2  minus brand aliases and credential vocabulary  (tests "is it login-page-ness")
  A3  function words only                            (tests pure register/style)
  A4  minus every token that appears in fewer than 1% of documents (tests long-tail memorisation)

If A1 stays high, the brand claim is dead. If A2 collapses, the signal is page ROLE, which
is a crawl artifact (phishing pages are login forms, legitimate pages are homepages) and not
phishing semantics. That distinction decides whether any brand-evidence arm is interpretable.
"""
import re
import sys

import numpy as np
import pandas as pd
import tldextract
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from urllib.parse import urlsplit

sys.path.insert(0, ".")
from audit_meta import load
from audit_matched import match

SEED = 20260812

# Credential / login vocabulary, multilingual because the corpus is not English-only.
CRED = {
    "login", "log", "signin", "sign", "logon", "password", "passwort", "passe", "senha",
    "contrasena", "contraseña", "pass", "pwd", "username", "user", "usuario", "utilisateur",
    "account", "conta", "cuenta", "konto", "compte", "email", "correo", "courriel",
    "verify", "verification", "verificar", "verifizieren", "confirm", "confirmar",
    "secure", "security", "seguridad", "sicherheit", "authenticate", "authentication",
    "credential", "credentials", "wallet", "seed", "phrase", "recovery", "restore",
    "bank", "banking", "banco", "banque", "card", "cartao", "tarjeta", "pin", "otp",
    "continue", "next", "submit", "enter", "entrar", "iniciar", "acceder", "anmelden",
    "connexion", "identifiant", "session", "unlock", "access",
}


def psl(host):
    e = tldextract.extract(str(host))
    return f"{e.domain}.{e.suffix}".strip(".").lower()


def build_aliases(bd):
    """Every string that plausibly names one of the 86 brands. Public-suffix aware, and
    generic tokens are excluded so we do not delete the whole corpus."""
    GENERIC = {"com", "net", "org", "www", "the", "inc", "ltd", "sa", "ag", "bank",
               "group", "online", "web", "mail", "cloud", "app", "id", "one", "co"}
    al = set()
    for _, r in bd.iterrows():
        ident = str(r["identifier"]).lower()
        name = str(r["name"]).lower()
        stem = tldextract.extract(str(r["website"])).domain.lower()
        cands = {ident, name, re.sub(r"[^a-z0-9]", "", name), stem}
        cands |= {w for w in re.split(r"[^a-z0-9]+", name) if w}
        al |= {c for c in cands if len(c) >= 4 and c not in GENERIC}
    return al


def strip_tokens(text, toks):
    if not toks:
        return text
    pat = re.compile(r"\b(" + "|".join(sorted(map(re.escape, toks), key=len, reverse=True)) + r")\b", re.I)
    return pat.sub(" ", text)


def score(name, texts, y, tr, te):
    v = TfidfVectorizer(analyzer="word", ngram_range=(1, 3), min_df=3, max_features=200000)
    Xt = v.fit_transform([texts[i] for i in tr])
    Xe = v.transform([texts[i] for i in te])
    lr = LogisticRegression(max_iter=4000).fit(Xt, y[tr])
    p, s = lr.predict(Xe), lr.predict_proba(Xe)[:, 1]
    print(f"  {name:52s} acc {accuracy_score(y[te],p):.3f}  F1 {f1_score(y[te],p):.3f}  "
          f"AUC {roc_auc_score(y[te],s):.3f}  vocab {len(v.vocabulary_):6d}")
    return accuracy_score(y[te], p)


def main():
    d = load()
    bd = pd.read_csv("brands.csv")
    aliases = build_aliases(bd)
    print(f"brand alias vocabulary: {len(aliases)} strings "
          f"(examples: {sorted(list(aliases))[:10]})")

    pairs = match(d)
    idx = [i for p in pairs for i in p]
    m = d.loc[idx].copy().reset_index(drop=True)
    y = m["y"].values
    # public-suffix-aware grouping, replacing the two-label reg()
    m["group2"] = m["host"].map(psl)
    print(f"size-matched set: {len(m)} rows, {y.sum()} phish / {(1-y).sum()} legit, "
          f"{m['group2'].nunique()} registrable domains (public-suffix aware)")

    gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED)
    tr, te = next(gss.split(m, y, groups=m["group2"]))
    from collections import Counter
    print(f"grouped split: test {len(te)}, majority {max(Counter(y[te]).values())/len(te):.3f}\n")

    base = m["text"].tolist()
    print("ABLATION LADDER")
    score("A0  full visible text", base, y, tr, te)
    a1 = [strip_tokens(t, aliases) for t in base]
    score("A1  minus brand aliases", a1, y, tr, te)
    a2 = [strip_tokens(t, CRED) for t in a1]
    score("A2  minus brand aliases + credential vocabulary", a2, y, tr, te)
    sw = set(ENGLISH_STOP_WORDS)
    a3 = [" ".join(w for w in re.split(r"[^A-Za-z]+", t) if w.lower() in sw) for t in base]
    score("A3  English function words only", a3, y, tr, te)

    # how much text does each ablation actually remove?
    print("\n  mean characters remaining, phish / legit:")
    for nm, txts in [("A0", base), ("A1", a1), ("A2", a2)]:
        L = np.array([len(t) for t in txts])
        print(f"    {nm}  {L[y==1].mean():8.0f} / {L[y==0].mean():8.0f}")

    # what survives A2 - print the strongest remaining features
    v = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=5, max_features=100000)
    X = v.fit_transform(a2)
    lr = LogisticRegression(max_iter=4000).fit(X, y)
    names = np.array(v.get_feature_names_out())
    co = lr.coef_[0]
    print("\n  after A2, top 20 tokens toward PHISHING:")
    print("   ", ", ".join(names[np.argsort(co)[-20:]][::-1]))
    print("  after A2, top 20 tokens toward LEGITIMATE:")
    print("   ", ", ".join(names[np.argsort(co)[:20]]))


if __name__ == "__main__":
    main()
