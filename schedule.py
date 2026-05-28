from datetime import datetime, timezone

# All kickoff times converted from ET (UTC-4) to UTC.

MATCHES = [

    # ================================================================== #
    #  GROUP A  —  Mexico, South Africa, South Korea, Czech Republic      #
    # ================================================================== #
    {"group": "A", "matchday": 1, "home": "Mexico",        "away": "South Africa",  "venue": "Mexico City",  "kickoff": datetime(2026,  6, 11, 19,  0, tzinfo=timezone.utc)},
    {"group": "A", "matchday": 1, "home": "South Korea",   "away": "Czech Republic","venue": "Guadalajara",  "kickoff": datetime(2026,  6, 12,  2,  0, tzinfo=timezone.utc)},
    {"group": "A", "matchday": 2, "home": "Czech Republic","away": "South Africa",  "venue": "Atlanta",      "kickoff": datetime(2026,  6, 18, 16,  0, tzinfo=timezone.utc)},
    {"group": "A", "matchday": 2, "home": "Mexico",        "away": "South Korea",   "venue": "Guadalajara",  "kickoff": datetime(2026,  6, 19,  1,  0, tzinfo=timezone.utc)},
    {"group": "A", "matchday": 3, "home": "Czech Republic","away": "Mexico",        "venue": "Mexico City",  "kickoff": datetime(2026,  6, 25,  1,  0, tzinfo=timezone.utc)},
    {"group": "A", "matchday": 3, "home": "South Africa",  "away": "South Korea",   "venue": "Monterrey",   "kickoff": datetime(2026,  6, 25,  1,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP B  —  Canada, Bosnia-Herzegovina, Qatar, Switzerland         #
    # ================================================================== #
    {"group": "B", "matchday": 1, "home": "Canada",             "away": "Bosnia-Herzegovina", "venue": "Toronto",     "kickoff": datetime(2026,  6, 12, 19,  0, tzinfo=timezone.utc)},
    {"group": "B", "matchday": 1, "home": "Qatar",              "away": "Switzerland",        "venue": "SF Bay Area", "kickoff": datetime(2026,  6, 13, 19,  0, tzinfo=timezone.utc)},
    {"group": "B", "matchday": 2, "home": "Switzerland",        "away": "Bosnia-Herzegovina", "venue": "Los Angeles", "kickoff": datetime(2026,  6, 18, 19,  0, tzinfo=timezone.utc)},
    {"group": "B", "matchday": 2, "home": "Canada",             "away": "Qatar",              "venue": "Vancouver",   "kickoff": datetime(2026,  6, 18, 22,  0, tzinfo=timezone.utc)},
    {"group": "B", "matchday": 3, "home": "Switzerland",        "away": "Canada",             "venue": "Vancouver",   "kickoff": datetime(2026,  6, 24, 19,  0, tzinfo=timezone.utc)},
    {"group": "B", "matchday": 3, "home": "Bosnia-Herzegovina", "away": "Qatar",              "venue": "Seattle",     "kickoff": datetime(2026,  6, 24, 19,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP C  —  Brazil, Morocco, Haiti, Scotland                       #
    # ================================================================== #
    {"group": "C", "matchday": 1, "home": "Brazil",   "away": "Morocco",  "venue": "New York/NJ",  "kickoff": datetime(2026,  6, 13, 22,  0, tzinfo=timezone.utc)},
    {"group": "C", "matchday": 1, "home": "Haiti",    "away": "Scotland", "venue": "Boston",       "kickoff": datetime(2026,  6, 14,  1,  0, tzinfo=timezone.utc)},
    {"group": "C", "matchday": 2, "home": "Scotland", "away": "Morocco",  "venue": "Boston",       "kickoff": datetime(2026,  6, 19, 22,  0, tzinfo=timezone.utc)},
    {"group": "C", "matchday": 2, "home": "Brazil",   "away": "Haiti",    "venue": "Philadelphia", "kickoff": datetime(2026,  6, 20,  1,  0, tzinfo=timezone.utc)},
    {"group": "C", "matchday": 3, "home": "Brazil",   "away": "Scotland", "venue": "Miami",        "kickoff": datetime(2026,  6, 24, 22,  0, tzinfo=timezone.utc)},
    {"group": "C", "matchday": 3, "home": "Morocco",  "away": "Haiti",    "venue": "Atlanta",      "kickoff": datetime(2026,  6, 24, 22,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP D  —  USA, Paraguay, Australia, Turkey                       #
    # ================================================================== #
    {"group": "D", "matchday": 1, "home": "USA",       "away": "Paraguay",  "venue": "Los Angeles", "kickoff": datetime(2026,  6, 13,  1,  0, tzinfo=timezone.utc)},
    {"group": "D", "matchday": 1, "home": "Australia", "away": "Turkey",    "venue": "Vancouver",   "kickoff": datetime(2026,  6, 13,  4,  0, tzinfo=timezone.utc)},
    {"group": "D", "matchday": 2, "home": "Turkey",    "away": "Paraguay",  "venue": "SF Bay Area", "kickoff": datetime(2026,  6, 19,  4,  0, tzinfo=timezone.utc)},
    {"group": "D", "matchday": 2, "home": "USA",       "away": "Australia", "venue": "Seattle",     "kickoff": datetime(2026,  6, 19, 19,  0, tzinfo=timezone.utc)},
    {"group": "D", "matchday": 3, "home": "Turkey",    "away": "USA",       "venue": "Los Angeles", "kickoff": datetime(2026,  6, 26,  2,  0, tzinfo=timezone.utc)},
    {"group": "D", "matchday": 3, "home": "Paraguay",  "away": "Australia", "venue": "SF Bay Area", "kickoff": datetime(2026,  6, 26,  2,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP E  —  Germany, Curacao, Ivory Coast, Ecuador                 #
    # ================================================================== #
    {"group": "E", "matchday": 1, "home": "Germany",     "away": "Curacao",     "venue": "Houston",      "kickoff": datetime(2026,  6, 14, 17,  0, tzinfo=timezone.utc)},
    {"group": "E", "matchday": 1, "home": "Ivory Coast", "away": "Ecuador",     "venue": "Philadelphia", "kickoff": datetime(2026,  6, 14, 23,  0, tzinfo=timezone.utc)},
    {"group": "E", "matchday": 2, "home": "Germany",     "away": "Ivory Coast", "venue": "Toronto",      "kickoff": datetime(2026,  6, 20, 20,  0, tzinfo=timezone.utc)},
    {"group": "E", "matchday": 2, "home": "Ecuador",     "away": "Curacao",     "venue": "Kansas City",  "kickoff": datetime(2026,  6, 21,  2,  0, tzinfo=timezone.utc)},
    {"group": "E", "matchday": 3, "home": "Curacao",     "away": "Ivory Coast", "venue": "Philadelphia", "kickoff": datetime(2026,  6, 25, 20,  0, tzinfo=timezone.utc)},
    {"group": "E", "matchday": 3, "home": "Ecuador",     "away": "Germany",     "venue": "New York/NJ",  "kickoff": datetime(2026,  6, 25, 20,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP F  —  Netherlands, Japan, Sweden, Tunisia                    #
    # ================================================================== #
    {"group": "F", "matchday": 1, "home": "Netherlands", "away": "Japan",       "venue": "Dallas",      "kickoff": datetime(2026,  6, 14, 20,  0, tzinfo=timezone.utc)},
    {"group": "F", "matchday": 1, "home": "Sweden",      "away": "Tunisia",     "venue": "Monterrey",   "kickoff": datetime(2026,  6, 15,  2,  0, tzinfo=timezone.utc)},
    {"group": "F", "matchday": 2, "home": "Tunisia",     "away": "Japan",       "venue": "Monterrey",   "kickoff": datetime(2026,  6, 20,  4,  0, tzinfo=timezone.utc)},
    {"group": "F", "matchday": 2, "home": "Netherlands", "away": "Sweden",      "venue": "Houston",     "kickoff": datetime(2026,  6, 20, 17,  0, tzinfo=timezone.utc)},
    {"group": "F", "matchday": 3, "home": "Japan",       "away": "Sweden",      "venue": "Dallas",      "kickoff": datetime(2026,  6, 25, 23,  0, tzinfo=timezone.utc)},
    {"group": "F", "matchday": 3, "home": "Tunisia",     "away": "Netherlands", "venue": "Kansas City", "kickoff": datetime(2026,  6, 25, 23,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP G  —  Belgium, Egypt, Iran, New Zealand                      #
    # ================================================================== #
    {"group": "G", "matchday": 1, "home": "Belgium",     "away": "Egypt",       "venue": "Seattle",     "kickoff": datetime(2026,  6, 15, 19,  0, tzinfo=timezone.utc)},
    {"group": "G", "matchday": 1, "home": "Iran",        "away": "New Zealand", "venue": "Los Angeles", "kickoff": datetime(2026,  6, 16,  1,  0, tzinfo=timezone.utc)},
    {"group": "G", "matchday": 2, "home": "Belgium",     "away": "Iran",        "venue": "Los Angeles", "kickoff": datetime(2026,  6, 21, 19,  0, tzinfo=timezone.utc)},
    {"group": "G", "matchday": 2, "home": "New Zealand", "away": "Egypt",       "venue": "Vancouver",   "kickoff": datetime(2026,  6, 22,  1,  0, tzinfo=timezone.utc)},
    {"group": "G", "matchday": 3, "home": "Egypt",       "away": "Iran",        "venue": "Seattle",     "kickoff": datetime(2026,  6, 27,  3,  0, tzinfo=timezone.utc)},
    {"group": "G", "matchday": 3, "home": "New Zealand", "away": "Belgium",     "venue": "Vancouver",   "kickoff": datetime(2026,  6, 27,  3,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP H  —  Spain, Cape Verde, Saudi Arabia, Uruguay               #
    # ================================================================== #
    {"group": "H", "matchday": 1, "home": "Spain",        "away": "Cape Verde",   "venue": "Atlanta",     "kickoff": datetime(2026,  6, 15, 16,  0, tzinfo=timezone.utc)},
    {"group": "H", "matchday": 1, "home": "Saudi Arabia", "away": "Uruguay",      "venue": "Miami",       "kickoff": datetime(2026,  6, 15, 22,  0, tzinfo=timezone.utc)},
    {"group": "H", "matchday": 2, "home": "Spain",        "away": "Saudi Arabia", "venue": "Atlanta",     "kickoff": datetime(2026,  6, 21, 16,  0, tzinfo=timezone.utc)},
    {"group": "H", "matchday": 2, "home": "Uruguay",      "away": "Cape Verde",   "venue": "Miami",       "kickoff": datetime(2026,  6, 21, 22,  0, tzinfo=timezone.utc)},
    {"group": "H", "matchday": 3, "home": "Cape Verde",   "away": "Saudi Arabia", "venue": "Houston",     "kickoff": datetime(2026,  6, 27,  0,  0, tzinfo=timezone.utc)},
    {"group": "H", "matchday": 3, "home": "Uruguay",      "away": "Spain",        "venue": "Guadalajara", "kickoff": datetime(2026,  6, 27,  0,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP I  —  France, Senegal, Iraq, Norway                          #
    # ================================================================== #
    {"group": "I", "matchday": 1, "home": "France",  "away": "Senegal", "venue": "New York/NJ",  "kickoff": datetime(2026,  6, 16, 19,  0, tzinfo=timezone.utc)},
    {"group": "I", "matchday": 1, "home": "Iraq",    "away": "Norway",  "venue": "Boston",       "kickoff": datetime(2026,  6, 16, 22,  0, tzinfo=timezone.utc)},
    {"group": "I", "matchday": 2, "home": "France",  "away": "Iraq",    "venue": "Philadelphia", "kickoff": datetime(2026,  6, 22, 21,  0, tzinfo=timezone.utc)},
    {"group": "I", "matchday": 2, "home": "Norway",  "away": "Senegal", "venue": "New York/NJ",  "kickoff": datetime(2026,  6, 23,  0,  0, tzinfo=timezone.utc)},
    {"group": "I", "matchday": 3, "home": "Norway",  "away": "France",  "venue": "Boston",       "kickoff": datetime(2026,  6, 26, 19,  0, tzinfo=timezone.utc)},
    {"group": "I", "matchday": 3, "home": "Senegal", "away": "Iraq",    "venue": "Toronto",      "kickoff": datetime(2026,  6, 26, 19,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP J  —  Argentina, Algeria, Austria, Jordan                    #
    # ================================================================== #
    {"group": "J", "matchday": 1, "home": "Austria",   "away": "Jordan",   "venue": "SF Bay Area", "kickoff": datetime(2026,  6, 16,  4,  0, tzinfo=timezone.utc)},
    {"group": "J", "matchday": 1, "home": "Argentina", "away": "Algeria",  "venue": "Kansas City", "kickoff": datetime(2026,  6, 17,  1,  0, tzinfo=timezone.utc)},
    {"group": "J", "matchday": 2, "home": "Argentina", "away": "Austria",  "venue": "Dallas",      "kickoff": datetime(2026,  6, 22, 17,  0, tzinfo=timezone.utc)},
    {"group": "J", "matchday": 2, "home": "Jordan",    "away": "Algeria",  "venue": "SF Bay Area", "kickoff": datetime(2026,  6, 23,  3,  0, tzinfo=timezone.utc)},
    {"group": "J", "matchday": 3, "home": "Algeria",   "away": "Austria",  "venue": "Kansas City", "kickoff": datetime(2026,  6, 28,  2,  0, tzinfo=timezone.utc)},
    {"group": "J", "matchday": 3, "home": "Jordan",    "away": "Argentina","venue": "Dallas",      "kickoff": datetime(2026,  6, 28,  2,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP K  —  Portugal, DR Congo, Uzbekistan, Colombia               #
    # ================================================================== #
    {"group": "K", "matchday": 1, "home": "Portugal",   "away": "DR Congo",   "venue": "Houston",     "kickoff": datetime(2026,  6, 17, 17,  0, tzinfo=timezone.utc)},
    {"group": "K", "matchday": 1, "home": "Uzbekistan", "away": "Colombia",   "venue": "Mexico City", "kickoff": datetime(2026,  6, 18,  2,  0, tzinfo=timezone.utc)},
    {"group": "K", "matchday": 2, "home": "Portugal",   "away": "Uzbekistan", "venue": "Houston",     "kickoff": datetime(2026,  6, 23, 17,  0, tzinfo=timezone.utc)},
    {"group": "K", "matchday": 2, "home": "Colombia",   "away": "DR Congo",   "venue": "Guadalajara", "kickoff": datetime(2026,  6, 24,  2,  0, tzinfo=timezone.utc)},
    {"group": "K", "matchday": 3, "home": "Colombia",   "away": "Portugal",   "venue": "Miami",       "kickoff": datetime(2026,  6, 27, 23, 30, tzinfo=timezone.utc)},
    {"group": "K", "matchday": 3, "home": "DR Congo",   "away": "Uzbekistan", "venue": "Atlanta",     "kickoff": datetime(2026,  6, 27, 23, 30, tzinfo=timezone.utc)},

    # ================================================================== #
    #  GROUP L  —  England, Croatia, Ghana, Panama                        #
    # ================================================================== #
    {"group": "L", "matchday": 1, "home": "England", "away": "Croatia", "venue": "Dallas",       "kickoff": datetime(2026,  6, 17, 20,  0, tzinfo=timezone.utc)},
    {"group": "L", "matchday": 1, "home": "Ghana",   "away": "Panama",  "venue": "Toronto",      "kickoff": datetime(2026,  6, 17, 23,  0, tzinfo=timezone.utc)},
    {"group": "L", "matchday": 2, "home": "England", "away": "Ghana",   "venue": "Boston",       "kickoff": datetime(2026,  6, 23, 20,  0, tzinfo=timezone.utc)},
    {"group": "L", "matchday": 2, "home": "Panama",  "away": "Croatia", "venue": "Toronto",      "kickoff": datetime(2026,  6, 23, 23,  0, tzinfo=timezone.utc)},
    {"group": "L", "matchday": 3, "home": "Panama",  "away": "England", "venue": "New York/NJ",  "kickoff": datetime(2026,  6, 27, 21,  0, tzinfo=timezone.utc)},
    {"group": "L", "matchday": 3, "home": "Croatia", "away": "Ghana",   "venue": "Philadelphia", "kickoff": datetime(2026,  6, 27, 21,  0, tzinfo=timezone.utc)},

    # ================================================================== #
    #  KNOCKOUT STAGE  —  add teams once group stage is done              #
    # ================================================================== #
    # Round of 32:   July 4–8
    # Round of 16:   July 10–13
    # Quarterfinals: July 15–16
    # Semifinals:    July 19–20
    # Third place:   July 22
    # Final:         July 26  —  MetLife Stadium, New Jersey
    #
    # {"group": "R32", "matchday": None, "home": "TBD", "away": "TBD",
    #  "venue": "TBD", "kickoff": datetime(2026, 7, 4, 23, 0, tzinfo=timezone.utc)},
]
