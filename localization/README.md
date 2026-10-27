# Language policy / Dil politikası

This fork supports Turkish and English. Desktop UI and guided interactions use Turkish and retain recognizable English engineering/API terminology. Technical documentation, source comments and docstrings use English. CLI/API diagnostics may be Turkish, English or bilingual. Turkish onboarding lives in [README.tr.md](../README.tr.md); shared terminology lives in [TERMS.tr-en.md](TERMS.tr-en.md).

Keep tool names, JSON keys, enum values, feature identifiers, file extensions and API signatures unchanged. Translate descriptions and messages, not protocol contracts. Match both Turkish and English natural-language inputs where a deterministic router is used.

Legacy localized CAD object names and OS error matching may be retained as escaped compatibility literals. These are runtime identifiers, not additional interface languages. Do not remove them solely to pass a text scan. Test paths containing non-ASCII characters remain useful.

Do not present upstream screenshots, binary installers or registry packages as localized releases. Preserve upstream/third-party attribution and original evidence URLs when they identify historical results. Active installation/update paths must target this fork or explicitly explain their upstream status.

Translation does not change units, tolerances, dimensional values, manufacturing standards, capability levels or acceptance gates. Native CAD validation must be rerun on the target environment before expanding compatibility claims.

Türkçe metinlerde teknik anlamı koruyun. İlk kullanımda “montaj ilişkisi (Mate)” gibi İngilizce karşılığı verin; komut ve API adlarını çevirmeyin. Teknik belgelerdeki bir sınırı yalnızca çeviri gerekçesiyle kaldırmayın.
