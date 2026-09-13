# International-coverage classification — version i3

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

`ukraine-russia`, `israel-gaza`, `middle-east-other`, `us-politics`,
`north-america`, `china`, `eu-politics`, `europe-other`, `uk-politics`,
`royals`, `migration`, `climate`, `economy-global`, `africa`, `asia-other`,
`latin-america`, `other`

Topic precedence when a story spans several:

- `israel-gaza` covers every story in which Israel, the Palestinian territories,
  or Israel's conflicts are a subject: Israeli politics and society, Gaza and the
  West Bank, Israel–Lebanon/Hezbollah, Israel–Iran, Houthi attacks on Israel,
  other states' sanctions on or deals with Israel, Israel-related protests and
  antisemitism rows abroad. If Israel is a party, use `israel-gaza`, not
  `middle-east-other` and not the other party's regional slug.
- `middle-east-other` is the rest of the region without Israel as a party: Iran
  internal affairs and Iran's confrontations with others, Syria, Iraq, the Gulf,
  Yemen, Turkey, Egypt.
- `ukraine-russia` covers the war and everything about it: sanctions on Russia,
  peace talks, arms deliveries, Russia's confrontations with Europe or NATO.
- `us-politics` (i3: now established) is the United States as a subject seen
  from abroad: its politics, government, elections, courts, major domestic
  events and anniversaries, presidential statements — Israel not a party.
- `north-america` (i3: new) is relations between the United States, Canada and
  Mexico as a bilateral or trilateral matter: the US–Canada trade war, tariffs,
  border disputes, USMCA. Mexico's or Canada's own internal affairs stay
  `latin-america` / `other`; a US outlet's story on Canada alone is `other`.
- `eu-politics` is the European Union's institutions and pan-EU politics.
- `europe-other` (i3: now established) is a single European country's own
  affairs seen from another outlet — a German coalition row on a French front
  page, a Spanish election in a UK paper — excluding the UK, Ukraine and Russia.
- `uk-politics` is the United Kingdom's own politics seen from abroad.
- `royals` (i3: new) is Europe's royal houses as the subject: a royal funeral,
  wedding, succession or scandal. For the home outlet its own royals are
  domestic (`null`).
- `economy-global`, `migration`, `climate` are for stories whose subject is the
  global theme itself (markets and oil prices, migration flows, climate policy
  and disasters) rather than one country's politics.

Worked examples (outlet home → verdict):

- UK → "Foreign secretary accused of antisemitism over Gaza remarks": international, `israel-gaza`.
- UK → "UK imposes trade ban on Israeli settlement goods": international, `israel-gaza`.
- US → "Senate passes budget after shutdown scare": domestic.
- UK → "US government shutdown enters third week": international, `us-politics`.
- US → "Trump bans range of Canadian products as trade war escalates": international, `north-america`.
- CA → "Canada and U.S. trade officials in contact, Champagne says": international, `north-america`.
- DE → "Trauerfeier für König Harald: Europas Royals in Oslo": international, `royals`.
- UK → "King leads royals at Windsor service": domestic.
- FR → "Coalition allemande : Merz sous pression": international, `europe-other`.
- EU → "Commission proposes new sanctions package against Russia": international, `ukraine-russia`.
- FR → "La France interdit l'importation des produits des colonies": international, `israel-gaza`.
- DE → "Bundestag streitet über Rentenreform": domestic.
- US → "Iran executes protesters amid crackdown": international, `middle-east-other`.
- US → "Oil tops $100 as Gulf tensions rattle markets": international, `economy-global`.

plus any additional currently-in-use slugs listed in the request. Mint a new
short kebab-case slug only when nothing established fits. Domestic items always
get topic `null`.
