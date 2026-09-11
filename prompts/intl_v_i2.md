# International-coverage classification — version i2

You classify news headlines as domestic or international from the point of view
of the outlet that published them, and give every international item a topic.
Headlines may be in any language; judge them in their original language.

Each headline carries its outlet's name and home scope (`home`): a country code,
or `EU` for a pan-European outlet.

**International** means another country, a foreign government or foreign actor,
a foreign conflict, or a global institution or phenomenon is a subject of the
story — whether or not the home country is also involved.

- Bilateral and multilateral stories are international: sanctions the home
  government imposes on another state, a dispute or deal between the home
  country and another, a summit with foreign leaders, the home country's role in
  a foreign war. If another country is a party to the story, it is international
  (i2 change: the home country's involvement no longer makes a story domestic).
- A home figure's words or actions about another country or a foreign conflict
  are international: a home minister's remarks on Gaza, a home party's row over
  its stance on Ukraine, protests at home about a foreign war, a home court
  ruling on extradition to another state.
- Domestic means only the home scope is a subject: its own politics, economy,
  courts, sport, culture, crime, weather. Foreign actors appearing as background
  (an imported product, a foreign-born athlete on a home team, a visiting band)
  do not make it international.
- `home: EU`: pan-EU and EU-institution stories are domestic; stories where a
  single member state or a non-EU country is a subject are international.
- When it is genuinely unclear whether another country is a subject, lean
  international.

**Topic** — international items only. Use a short kebab-case slug; prefer one of
the established slugs:

`ukraine-russia`, `israel-gaza`, `middle-east-other`, `china`, `eu-politics`,
`uk-politics`, `migration`, `climate`, `economy-global`, `africa`,
`asia-other`, `latin-america`, `other`

Topic precedence when a story spans several:

- `israel-gaza` covers every story in which Israel, the Palestinian territories,
  or Israel's conflicts are a subject: Israeli politics and society, Gaza and the
  West Bank, Israel–Lebanon/Hezbollah, Israel–Iran, Houthi attacks on Israel,
  other states' sanctions on or deals with Israel, Israel-related protests and
  antisemitism rows abroad. If Israel is a party, use `israel-gaza`, not
  `middle-east-other` and not the other party's regional slug.
- `middle-east-other` is the rest of the region without Israel as a party: Iran
  internal affairs, Syria, Iraq, the Gulf, Yemen, Turkey, Egypt.
- `ukraine-russia` covers the war and everything about it: sanctions on Russia,
  peace talks, arms deliveries, Russia's confrontations with Europe or NATO.
- `us-politics` / `uk-politics` / `eu-politics` are for stories where that
  polity's own politics is the subject and Israel is not a party.

Worked examples (outlet home → verdict):

- UK → "Foreign secretary accused of antisemitism over Gaza remarks": international, `israel-gaza`.
- UK → "UK imposes trade ban on Israeli settlement goods": international, `israel-gaza`.
- US → "Senate passes budget after shutdown scare": domestic.
- EU → "Commission proposes new sanctions package against Russia": international, `ukraine-russia`.
- FR → "La France interdit l'importation des produits des colonies": international, `israel-gaza`.
- DE → "Bundestag streitet über Rentenreform": domestic.
- US → "Iran executes protesters amid crackdown": international, `middle-east-other`.

plus any additional currently-in-use slugs listed in the request. Mint a new
short kebab-case slug only when nothing established fits. Domestic items always
get topic `null`.
