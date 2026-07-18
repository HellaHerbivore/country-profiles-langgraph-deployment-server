"""Canonical intervention-tag taxonomy for the Movement Map file store.

Codes and labels come from Stray Dog Institute's State of the Movement survey
(the ACE Movement Map's interventions menu derives from the same survey). The
converter pipelines expand codes into these labels inside each org profile and
attach the raw codes as `intervention_tags` custom metadata; the internal
researcher builds metadata filters from the codes for exact-tag retrieval.

Stdlib-only: imported both by the deployed graph (internal_researcher.py) and
by the offline converter/verify scripts under scripts/filestore_scripts/.
"""

INTERVENTION_TAGS: dict[str, str] = {
    "GOV-Food": "Government — Food policy advocacy (nutrition guidelines, health policy, alt-protein regulation)",
    "GOV-Ag": "Government — Agricultural policy advocacy (programs, subsidies, land use)",
    "GOV-Env": "Government — Environmental policy advocacy",
    "GOV-Animal": "Government — Animal policy advocacy (welfare lobbying or lawsuits)",
    "GOV-Elections": "Government — Electioneering",
    "BIZ-Producer": "Business — Producer outreach (farmers, producers)",
    "BIZ-Litigation": "Business — Corporate litigation",
    "BIZ-VegEngage": "Business — Corporate & institutional engagement: veg*n outreach",
    "BIZ-WelfareEngage": "Business — Corporate & institutional engagement: welfare improvements",
    "BIZ-InfluenceInvest": "Business — Finance: influencing investment",
    "BIZ-ProvideInvest": "Business — Finance: providing investment",
    "BIZ-Labeling": "Business — Product labeling and certification",
    "PUB-Media": "Public — Books, documentaries and other films, podcasts",
    "PUB-Influencer": "Public — Celebrity and influencer outreach",
    "PUB-Education": "Public — School or university classes, academic programs, university partnerships",
    "PUB-Investigations": "Public — Investigations",
    "PUB-Journalism": "Public — Journalism and mainstream-media outreach",
    "PUB-Ads": "Public — Physical advertising",
    "PUB-Protest": "Public — Mass mobilizations and protests",
    "PUB-Digital": "Public — Digital outreach (social campaigns, online ads, apps, pledges)",
    "PUB-Events": "Public — Conferences and public events",
    "MVT-InfluenceFunding": "Movement — Funding: influencing funding",
    "MVT-Funding": "Movement — Funding: providing funding",
    "MVT-Network": "Movement — Network building (coalitions, collaboration)",
    "MVT-Research": "Movement — Research (surveys, analyses, peer-reviewed work, tools)",
    "MVT-Training": "Movement — Skill building (training programs, staff education)",
    "MVT-MonitorEval": "Movement — Monitoring and evaluation",
    "MVT-ProServices": "Movement — Professional services (legal, technical)",
    "ANI-Sanctuary": "Animals — Sanctuaries, veterinary care, and rehabilitation",
    "ANI-Rescue": "Animals — Rescue and direct action",
    "OTHER": "Other (described in the profile's notes)",
}

# custom_metadata key carrying the tag codes (string_list_value) on every
# Movement Map document, both collections.
METADATA_KEY = "intervention_tags"


def build_tag_filter(codes: list[str]) -> str:
    """Metadata filter matching documents whose tag list contains ANY given code.

    AIP-160 grammar: `:` is the "has" operator, which is membership for
    string_list_value metadata. verify_profiles.py exercises this expression
    (including the OR form) against the live store — if the grammar ever needs
    adjusting, this function is the only place to change.
    """
    terms = [f'{METADATA_KEY}:"{code}"' for code in codes if code in INTERVENTION_TAGS]
    return " OR ".join(terms)
