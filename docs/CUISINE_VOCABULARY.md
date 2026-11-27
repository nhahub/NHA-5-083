# Cuisine Vocabulary

> **Status:** Draft v0.1, a living document. Built from the 145 distinct cuisine labels in the Zomato dataset (`data/zomato.csv`, 9,551 rows).
> **Last updated:** 2026-11-24

The canonical cuisine vocabulary used by the standardize step, the cuisine filter, and the NLP vocabulary check. It has two levels:

- **Canonical cuisine** (130 names): the value stored in `cuisines.cuisine_name`. Most Zomato labels map to themselves; a few rare synonyms and mis-encoded labels are merged.
- **Cuisine group** (15 groups): a broader family for filtering and summaries, and the anchor for mapping other sources later.

During implementation, the machine-readable form of this table lives in one file (for example `config/cuisine_map.csv`, columns `source_label,canonical_cuisine,cuisine_group`) that the pipeline loads; this document is regenerated from it or kept in step with it in the same pull request.

## 1. Normalization rules

1. Split the source field on commas; trim whitespace; drop empty items.
2. Repair known mis-encoded labels before lookup (`Dï¿½_ner` becomes `Döner`, `Bï¿½_rek` becomes `Börek`).
3. Look up the label in the merge table below (case-sensitive after trimming).
4. A label not in the vocabulary is **kept as is** and flagged with the warning `cuisine_unmapped` (`DATA_QUALITY_RULES.md`). It is never dropped, and it does not reject the record.
5. Remove duplicate canonical names for one restaurant after merging (for example `Tea` and `Coffee and Tea` on the same record become one `Coffee & Tea`).

## 2. Merges

Only these labels change; every other Zomato label maps to itself.

| Source label | Canonical cuisine | Reason |
| --- | --- | --- |
| `Malay` | Malaysian | Synonym |
| `Sunda` | Indonesian | Regional cuisine with one record |
| `Turkish Pizza`, `Izgara`, `Döner`, `Börek` | Turkish | Turkish dishes with very few records |
| `Iranian` | Persian | Synonym |
| `Durban` | South African | City-style label |
| `Mineira` | Brazilian | Regional cuisine with one record |
| `Kiwi` | New Zealand | Clearer name |
| `World Cuisine`, `Cuisine Varies` | International | Synonyms |
| `Gourmet Fast Food` | Fast Food | Synonym |
| `Charcoal Grill` | Grill | Synonym |
| `Restaurant Cafe` | Cafe | Synonym |
| `Coffee and Tea`, `Tea` | Coffee & Tea | Same venue type |

## 3. Vocabulary by group

Row counts are the number of Zomato restaurants listing that cuisine (a restaurant can list several).

### Indian

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| North Indian | | 3960 |
| Mughlai | | 995 |
| South Indian | | 636 |
| Biryani | | 177 |
| Indian | | 70 |
| Bengali | | 29 |
| Hyderabadi | | 26 |
| Kerala | | 23 |
| Rajasthani | | 21 |
| Kashmiri | | 20 |
| Goan | | 20 |
| Modern Indian | | 16 |
| Lucknowi | | 13 |
| Awadhi | | 11 |
| Gujarati | | 11 |
| Chettinad | | 11 |
| Maharashtrian | | 10 |
| Andhra | | 10 |
| North Eastern | | 9 |
| Naga | | 8 |
| Parsi | | 8 |
| Bihari | | 6 |
| Curry | | 6 |
| Mangalorean | | 4 |
| Assamese | | 4 |
| Oriya | | 2 |
| Malwani | | 1 |

### South Asian (other)

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Tibetan | | 44 |
| Afghani | | 14 |
| Pakistani | | 12 |
| Nepalese | | 9 |
| Sri Lankan | | 5 |

### East Asian

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Chinese | | 2735 |
| Japanese | | 135 |
| Sushi | | 75 |
| Korean | | 21 |
| Dim Sum | | 3 |
| Cantonese | | 2 |
| Taiwanese | | 2 |
| Ramen | | 2 |
| Teriyaki | | 2 |

### Southeast Asian

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Thai | | 234 |
| Malaysian | `Malay` | 23 |
| Vietnamese | | 21 |
| Indonesian | `Sunda` | 17 |
| Filipino | | 10 |
| Burmese | | 10 |
| Singaporean | | 4 |
| Peranakan | | 1 |

### Pan-Asian

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Asian | | 233 |
| Asian Fusion | | 2 |

### Middle Eastern and Turkish

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Lebanese | | 69 |
| Arabian | | 28 |
| Turkish | `Turkish Pizza`, `Izgara`, `Döner`, `Börek` | 27 |
| Middle Eastern | | 22 |
| Kebab | | 10 |
| Persian | `Iranian` | 5 |
| Armenian | | 3 |

### African

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| African | | 8 |
| South African | `Durban` | 7 |
| Moroccan | | 5 |

### European

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Italian | | 764 |
| Continental | | 736 |
| European | | 148 |
| Mediterranean | | 112 |
| French | | 29 |
| Tapas | | 19 |
| Spanish | | 16 |
| British | | 16 |
| Greek | | 15 |
| German | | 10 |
| Portuguese | | 7 |
| Scottish | | 3 |
| Belgian | | 2 |
| Irish | | 1 |
| Fish and Chips | | 1 |

### North American

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| American | | 390 |
| Southern | | 24 |
| Tex-Mex | | 19 |
| Cajun | | 10 |
| Hawaiian | | 8 |
| Southwestern | | 7 |
| Diner | | 6 |
| New American | | 2 |
| Soul Food | | 1 |
| Canadian | | 1 |

### Latin American and Caribbean

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Mexican | | 181 |
| Brazilian | `Mineira` | 29 |
| Latin American | | 11 |
| Caribbean | | 7 |
| South American | | 2 |
| Argentine | | 2 |
| Cuban | | 2 |
| Peruvian | | 1 |

### Oceanian

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Modern Australian | | 11 |
| New Zealand | `Kiwi` | 6 |
| Australian | | 5 |

### International and Fusion

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| International | `World Cuisine`, `Cuisine Varies` | 26 |
| Western | | 10 |
| Contemporary | | 9 |
| Fusion | | 4 |

### Dish and Format

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Fast Food | `Gourmet Fast Food` | 1987 |
| Street Food | | 562 |
| Pizza | | 381 |
| Burger | | 251 |
| Seafood | | 174 |
| Healthy Food | | 150 |
| Finger Food | | 114 |
| Raw Meats | | 114 |
| Salad | | 93 |
| Steak | | 62 |
| Sandwich | | 53 |
| Breakfast | | 41 |
| Bar Food | | 39 |
| BBQ | | 33 |
| Grill | `Charcoal Grill` | 25 |
| Vegetarian | | 23 |
| Deli | | 3 |
| Pub Food | | 2 |

### Bakery and Desserts

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Bakery | | 745 |
| Desserts | | 653 |
| Mithai | | 380 |
| Ice Cream | | 226 |
| Patisserie | | 4 |

### Cafe and Beverages

| Canonical cuisine | Merged source labels | Zomato rows |
| --- | --- | ---: |
| Cafe | `Restaurant Cafe` | 707 |
| Beverages | | 229 |
| Coffee & Tea | `Coffee and Tea`, `Tea` | 67 |
| Juices | | 29 |
| Drinks Only | | 2 |
| Bubble Tea | | 1 |

## 4. Future sources (low priority)

Other sources use different category systems (Overture's place taxonomy, OpenStreetMap's free-form `cuisine` tag). When a second source is integrated, a standardized mapping table from each source's categories to the canonical cuisine and group above is required for merging. This is a low-priority task, deferred until then (decision D-9 in `ARCHITECTURE.md`).

## 5. Change log

| Date | Change |
| --- | --- |
| 2026-11-24 | v0.1 created from the Zomato dataset: 145 source labels mapped to 130 canonical cuisines in 15 groups; normalization and merge rules |
