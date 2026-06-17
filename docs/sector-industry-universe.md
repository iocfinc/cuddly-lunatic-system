# HK/US Sector and Industry Universe

Generated: `2026-04-29T23:54:42+00:00`

This is the working taxonomy for Quant Researcher Desk supply-chain research. It uses Moomoo OpenAPI plate lists as the live market taxonomy, then adds a local research layer for domains, value-chain roles, and graph edges.

## Source Notes

- Moomoo `get_plate_list(market, plate_class)` returns plate code, plate name, and plate ID for market sector lists: https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-plate-list.html
- Moomoo `get_plate_stock(plate_code)` can expand any plate into constituent stocks when a report needs a company list: https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-plate-stock.html
- GICS remains the global comparison frame: sectors, industry groups, industries, and sub-industries: https://www.msci.com/indexes/index-resources/gics
- For Hong Kong listed-company context, HSICS is the exchange-facing industry classification lineage; HKEX adopted HSICS for all Hong Kong-listed companies: https://www.hkex.com.hk/News/News-Release/2007/071211news

## Coverage Summary

| Market | Plate type | Count |
| --- | ---: | ---: |
| HK | ALL | 67 |
| HK | CONCEPT | 117 |
| HK | INDUSTRY | 111 |
| US | ALL | 90 |
| US | CONCEPT | 113 |
| US | INDUSTRY | 145 |

## Domain Coverage

| Domain | Plates |
| --- | ---: |
| Other / Cross-sector | 294 |
| Technology & Telecom | 57 |
| Energy & Utilities | 46 |
| Consumer | 45 |
| Industrials & Manufacturing | 42 |
| Financials | 34 |
| Materials | 27 |
| Agriculture & Food | 25 |
| Healthcare | 25 |
| Transportation & Logistics | 20 |
| Real Estate & Infrastructure | 17 |
| Media & Entertainment | 7 |
| Environmental Services | 4 |

## Priority Industry Rotation Candidates

These are the live Moomoo industry plates that classify cleanly into an upstream, midstream, or downstream role. They should be the first expansion set for the 3-hour sector cron before lower-signal concept and region plates.

| Market | Code | Industry | Domain | Role |
| --- | --- | --- | --- | --- |
| HK | `HK.LIST1011` | Agricultural Inputs | Agriculture & Food | upstream |
| HK | `HK.LIST1008` | Agriculture | Agriculture & Food | upstream |
| HK | `HK.LIST1072` | Alcoholic Beverages | Agriculture & Food | downstream |
| HK | `HK.LIST1083` | Catering | Agriculture & Food | downstream |
| HK | `HK.LIST1082` | Food Additives | Agriculture & Food | midstream |
| HK | `HK.LIST1272` | Livestock Feed | Agriculture & Food | upstream |
| HK | `HK.LIST1080` | Non-Alcoholic Beverages | Agriculture & Food | downstream |
| HK | `HK.LIST1070` | Supermarkets & Convenience Stores | Agriculture & Food | downstream |
| HK | `HK.LIST1010` | packaged food | Agriculture & Food | midstream |
| HK | `HK.LIST1270` | Apparel Retailers | Consumer | downstream |
| HK | `HK.LIST1269` | Auto Retailers | Consumer | downstream |
| HK | `HK.LIST1052` | Consumer Electronics | Consumer | downstream |
| HK | `HK.LIST1056` | Diversified Retailers | Consumer | downstream |
| HK | `HK.LIST1275` | Footwear | Consumer | downstream |
| HK | `HK.LIST1359` | Gaming | Consumer | downstream |
| HK | `HK.LIST1022` | Home Appliances | Consumer | downstream |
| HK | `HK.LIST1278` | Home Improvement Retail | Consumer | downstream |
| HK | `HK.LIST1071` | Hotels & Resorts | Consumer | downstream |
| HK | `HK.LIST1049` | Jewelry & Watches | Consumer | downstream |
| HK | `HK.LIST23361` | Online Retailers | Consumer | downstream |
| HK | `HK.LIST1276` | Other Retailers | Consumer | downstream |
| HK | `HK.LIST1069` | Resorts & Casinos | Consumer | downstream |
| HK | `HK.LIST1034` | Travel & Sightseeing | Consumer | downstream |
| HK | `HK.LIST1044` | Coal | Energy & Utilities | upstream |
| HK | `HK.LIST1051` | Electric Utilities | Energy & Utilities | midstream |
| HK | `HK.LIST1045` | Gas Utilities | Energy & Utilities | midstream |
| HK | `HK.LIST1042` | Oil & Gas Producers | Energy & Utilities | upstream |
| HK | `HK.LIST1039` | Water Utilities | Energy & Utilities | midstream |
| HK | `HK.LIST1050` | Biotechnology | Healthcare | midstream |
| HK | `HK.LIST1067` | Pharmaceuticals | Healthcare | midstream |
| HK | `HK.LIST1277` | Apparel Manufacturing | Industrials & Manufacturing | downstream |
| HK | `HK.LIST1053` | Computers & Equipment | Industrials & Manufacturing | midstream |
| HK | `HK.LIST1055` | Consumer Telecommunication Equipment | Industrials & Manufacturing | downstream |
| HK | `HK.LIST1095` | Engineering & Construction | Industrials & Manufacturing | midstream |
| HK | `HK.LIST1074` | Heavy Machinery | Industrials & Manufacturing | midstream |
| HK | `HK.LIST1025` | Industrial Parts & Equipment | Industrials & Manufacturing | midstream |
| HK | `HK.LIST1012` | Medical Equipment & Supplies | Industrials & Manufacturing | midstream |
| HK | `HK.LIST1015` | Printing & Packaging | Industrials & Manufacturing | midstream |
| HK | `HK.LIST1360` | Semiconductor Equipment & Materials | Industrials & Manufacturing | midstream |
| HK | `HK.LIST23846` | Track and train equipment | Industrials & Manufacturing | midstream |
| HK | `HK.LIST1078` | Aluminum | Materials | upstream |
| HK | `HK.LIST1028` | Construction Materials | Materials | midstream |
| HK | `HK.LIST1077` | Copper | Materials | upstream |
| HK | `HK.LIST1037` | Forestry & Timber | Materials | upstream |
| HK | `HK.LIST1084` | Gold & Precious Metals | Materials | upstream |
| HK | `HK.LIST1006` | Other Metals & Minerals | Materials | upstream |
| HK | `HK.LIST1059` | Paper & Packaging | Materials | upstream |
| HK | `HK.LIST1046` | Speciality Chemicals | Materials | upstream |
| HK | `HK.LIST1100` | Application Software | Technology & Telecom | midstream |
| HK | `HK.LIST1274` | Electronic Components | Technology & Telecom | midstream |
| HK | `HK.LIST23360` | Interactive media and services | Technology & Telecom | downstream |
| HK | `HK.LIST23364` | Internet services and infrastructure | Technology & Telecom | midstream |
| HK | `HK.LIST1013` | Semiconductors | Technology & Telecom | midstream |
| HK | `HK.LIST1065` | Air Cargo & Logistics | Transportation & Logistics | midstream |
| HK | `HK.LIST1005` | Public Transport | Transportation & Logistics | midstream |
| HK | `HK.LIST1355` | Transport & Logistics | Transportation & Logistics | midstream |
| US | `US.LIST2010` | Agricultural Inputs | Agriculture & Food | upstream |
| US | `US.LIST2427` | Beverages - Brewers | Agriculture & Food | downstream |
| US | `US.LIST2459` | Beverages - Non-Alcoholic | Agriculture & Food | downstream |
| US | `US.LIST2464` | Beverages - Wineries & Distilleries | Agriculture & Food | downstream |
| US | `US.LIST2108` | Packaged Foods | Agriculture & Food | midstream |
| US | `US.LIST2494` | Apparel Retail | Consumer | downstream |
| US | `US.LIST2075` | Consumer Electronics | Consumer | downstream |
| US | `US.LIST2253` | Electronic Gaming & Multimedia | Consumer | downstream |
| US | `US.LIST2106` | Footwear & Accessories | Consumer | downstream |
| US | `US.LIST2460` | Home Improvement Retail | Consumer | downstream |
| US | `US.LIST2431` | Internet Retail | Consumer | downstream |
| US | `US.LIST2092` | Pharmaceutical Retailers | Consumer | downstream |
| US | `US.LIST2475` | REIT - Hotel & Motel | Consumer | downstream |
| US | `US.LIST2141` | REIT - Retail | Consumer | downstream |
| US | `US.LIST2046` | Resorts & Casinos | Consumer | downstream |
| US | `US.LIST2502` | Specialty Retail | Consumer | downstream |
| US | `US.LIST2498` | Travel Services | Consumer | downstream |
| US | `US.LIST2505` | Coking Coal | Energy & Utilities | upstream |
| US | `US.LIST2257` | Oil & Gas Equipment & Services | Energy & Utilities | midstream |
| US | `US.LIST2487` | Thermal Coal | Energy & Utilities | upstream |
| US | `US.LIST2489` | Utilities - Regulated Gas | Energy & Utilities | midstream |
| US | `US.LIST2461` | Utilities - Renewable | Energy & Utilities | midstream |
| US | `US.LIST2458` | Utilities - Regulated Water | Environmental Services | midstream |
| US | `US.LIST2069` | Biotechnology | Healthcare | midstream |
| US | `US.LIST2049` | Apparel Manufacturing | Industrials & Manufacturing | downstream |
| US | `US.LIST2468` | Auto Manufacturers | Industrials & Manufacturing | midstream |
| US | `US.LIST2483` | Building Products & Equipment | Industrials & Manufacturing | midstream |
| US | `US.LIST2509` | Business Equipment & Supplies | Industrials & Manufacturing | midstream |
| US | `US.LIST2098` | Communication Equipment | Industrials & Manufacturing | midstream |
| US | `US.LIST2428` | Drug Manufacturers - General | Industrials & Manufacturing | midstream |
| US | `US.LIST2513` | Drug Manufacturers - Specialty & Generic | Industrials & Manufacturing | midstream |
| US | `US.LIST2493` | Electrical Equipment & Parts | Industrials & Manufacturing | midstream |
| US | `US.LIST2033` | Engineering & Construction | Industrials & Manufacturing | midstream |
| US | `US.LIST2471` | Farm & Heavy Construction Machinery | Industrials & Manufacturing | midstream |
| US | `US.LIST2237` | Packaging & Containers | Industrials & Manufacturing | midstream |
| US | `US.LIST2005` | Residential Construction | Industrials & Manufacturing | midstream |
| US | `US.LIST2016` | Semiconductor Equipment & Materials | Industrials & Manufacturing | midstream |
| US | `US.LIST2463` | Specialty Industrial Machinery | Industrials & Manufacturing | midstream |
| US | `US.LIST2499` | Textile Manufacturing | Industrials & Manufacturing | midstream |
| US | `US.LIST2211` | Aluminum | Materials | upstream |
| US | `US.LIST2020` | Chemicals | Materials | upstream |
| US | `US.LIST2510` | Copper | Materials | upstream |
| US | `US.LIST2110` | Gold | Materials | upstream |
| US | `US.LIST2270` | Metal Fabrication | Materials | upstream |
| US | `US.LIST2501` | Other Industrial Metals & Mining | Materials | upstream |
| US | `US.LIST2507` | Other Precious Metals & Mining | Materials | upstream |
| US | `US.LIST2083` | Paper & Paper Products | Materials | upstream |
| US | `US.LIST2068` | Specialty Chemicals | Materials | upstream |
| US | `US.LIST2488` | Utilities - Diversified | Other / Cross-sector | midstream |
| US | `US.LIST2462` | Utilities - Independent Power Producers | Other / Cross-sector | midstream |
| US | `US.LIST2472` | Utilities - Regulated Electric | Other / Cross-sector | midstream |
| US | `US.LIST2072` | Electronic Components | Technology & Telecom | midstream |
| US | `US.LIST2015` | Semiconductors | Technology & Telecom | midstream |
| US | `US.LIST2470` | Software - Application | Technology & Telecom | midstream |
| US | `US.LIST2508` | Software - Infrastructure | Technology & Telecom | midstream |
| US | `US.LIST2500` | Integrated Freight & Logistics | Transportation & Logistics | midstream |

## All Moomoo Industry Plates

| Market | Code | Industry | Domain | Role | Priority |
| --- | --- | --- | --- | --- | ---: |
| HK | `HK.LIST1011` | Agricultural Inputs | Agriculture & Food | upstream | 1 |
| HK | `HK.LIST1008` | Agriculture | Agriculture & Food | upstream | 1 |
| HK | `HK.LIST1072` | Alcoholic Beverages | Agriculture & Food | downstream | 1 |
| HK | `HK.LIST1083` | Catering | Agriculture & Food | downstream | 1 |
| HK | `HK.LIST1082` | Food Additives | Agriculture & Food | midstream | 1 |
| HK | `HK.LIST1272` | Livestock Feed | Agriculture & Food | upstream | 1 |
| HK | `HK.LIST1080` | Non-Alcoholic Beverages | Agriculture & Food | downstream | 1 |
| HK | `HK.LIST1070` | Supermarkets & Convenience Stores | Agriculture & Food | downstream | 1 |
| HK | `HK.LIST1010` | packaged food | Agriculture & Food | midstream | 1 |
| HK | `HK.LIST1270` | Apparel Retailers | Consumer | downstream | 1 |
| HK | `HK.LIST1269` | Auto Retailers | Consumer | downstream | 1 |
| HK | `HK.LIST1052` | Consumer Electronics | Consumer | downstream | 1 |
| HK | `HK.LIST1056` | Diversified Retailers | Consumer | downstream | 1 |
| HK | `HK.LIST1275` | Footwear | Consumer | downstream | 1 |
| HK | `HK.LIST1359` | Gaming | Consumer | downstream | 1 |
| HK | `HK.LIST1022` | Home Appliances | Consumer | downstream | 1 |
| HK | `HK.LIST1278` | Home Improvement Retail | Consumer | downstream | 1 |
| HK | `HK.LIST1071` | Hotels & Resorts | Consumer | downstream | 1 |
| HK | `HK.LIST1049` | Jewelry & Watches | Consumer | downstream | 1 |
| HK | `HK.LIST23361` | Online Retailers | Consumer | downstream | 1 |
| HK | `HK.LIST1276` | Other Retailers | Consumer | downstream | 1 |
| HK | `HK.LIST1069` | Resorts & Casinos | Consumer | downstream | 1 |
| HK | `HK.LIST1034` | Travel & Sightseeing | Consumer | downstream | 1 |
| HK | `HK.LIST1044` | Coal | Energy & Utilities | upstream | 1 |
| HK | `HK.LIST1051` | Electric Utilities | Energy & Utilities | midstream | 1 |
| HK | `HK.LIST1045` | Gas Utilities | Energy & Utilities | midstream | 1 |
| HK | `HK.LIST1042` | Oil & Gas Producers | Energy & Utilities | upstream | 1 |
| HK | `HK.LIST1039` | Water Utilities | Energy & Utilities | midstream | 1 |
| HK | `HK.LIST1050` | Biotechnology | Healthcare | midstream | 1 |
| HK | `HK.LIST1067` | Pharmaceuticals | Healthcare | midstream | 1 |
| HK | `HK.LIST1277` | Apparel Manufacturing | Industrials & Manufacturing | downstream | 1 |
| HK | `HK.LIST1053` | Computers & Equipment | Industrials & Manufacturing | midstream | 1 |
| HK | `HK.LIST1055` | Consumer Telecommunication Equipment | Industrials & Manufacturing | downstream | 1 |
| HK | `HK.LIST1095` | Engineering & Construction | Industrials & Manufacturing | midstream | 1 |
| HK | `HK.LIST1074` | Heavy Machinery | Industrials & Manufacturing | midstream | 1 |
| HK | `HK.LIST1025` | Industrial Parts & Equipment | Industrials & Manufacturing | midstream | 1 |
| HK | `HK.LIST1012` | Medical Equipment & Supplies | Industrials & Manufacturing | midstream | 1 |
| HK | `HK.LIST1015` | Printing & Packaging | Industrials & Manufacturing | midstream | 1 |
| HK | `HK.LIST1360` | Semiconductor Equipment & Materials | Industrials & Manufacturing | midstream | 1 |
| HK | `HK.LIST23846` | Track and train equipment | Industrials & Manufacturing | midstream | 1 |
| HK | `HK.LIST1078` | Aluminum | Materials | upstream | 1 |
| HK | `HK.LIST1028` | Construction Materials | Materials | midstream | 1 |
| HK | `HK.LIST1077` | Copper | Materials | upstream | 1 |
| HK | `HK.LIST1037` | Forestry & Timber | Materials | upstream | 1 |
| HK | `HK.LIST1084` | Gold & Precious Metals | Materials | upstream | 1 |
| HK | `HK.LIST1006` | Other Metals & Minerals | Materials | upstream | 1 |
| HK | `HK.LIST1059` | Paper & Packaging | Materials | upstream | 1 |
| HK | `HK.LIST1046` | Speciality Chemicals | Materials | upstream | 1 |
| HK | `HK.LIST1100` | Application Software | Technology & Telecom | midstream | 1 |
| HK | `HK.LIST1274` | Electronic Components | Technology & Telecom | midstream | 1 |
| HK | `HK.LIST23360` | Interactive media and services | Technology & Telecom | downstream | 1 |
| HK | `HK.LIST23364` | Internet services and infrastructure | Technology & Telecom | midstream | 1 |
| HK | `HK.LIST1013` | Semiconductors | Technology & Telecom | midstream | 1 |
| HK | `HK.LIST1065` | Air Cargo & Logistics | Transportation & Logistics | midstream | 1 |
| HK | `HK.LIST1005` | Public Transport | Transportation & Logistics | midstream | 1 |
| HK | `HK.LIST1355` | Transport & Logistics | Transportation & Logistics | midstream | 1 |
| HK | `HK.LIST1001` | Dairy | Agriculture & Food | cross_chain | 2 |
| HK | `HK.LIST1273` | Meat & Poultry | Agriculture & Food | cross_chain | 2 |
| HK | `HK.LIST1356` | Tobacco | Agriculture & Food | cross_chain | 2 |
| HK | `HK.LIST1062` | Personal Care | Consumer | cross_chain | 2 |
| HK | `HK.LIST23850` | Skincare and cosmetics | Consumer | cross_chain | 2 |
| HK | `HK.LIST1047` | Toys & Leisure | Consumer | cross_chain | 2 |
| HK | `HK.LIST1021` | furniture | Consumer | cross_chain | 2 |
| HK | `HK.LIST1016` | Alternative/Renewable Energy | Energy & Utilities | cross_chain | 2 |
| HK | `HK.LIST1354` | Energy Storage Systems | Energy & Utilities | cross_chain | 2 |
| HK | `HK.LIST1033` | New Energy Materials | Energy & Utilities | cross_chain | 2 |
| HK | `HK.LIST1043` | Oil & Gas Services | Energy & Utilities | cross_chain | 2 |
| HK | `HK.LIST1358` | nuclear | Energy & Utilities | cross_chain | 2 |
| HK | `HK.LIST1271` | Environmental Services | Environmental Services | cross_chain | 2 |
| HK | `HK.LIST1079` | Banks | Financials | enabler | 2 |
| HK | `HK.LIST1004` | Credit Services | Financials | enabler | 2 |
| HK | `HK.LIST1003` | Insurance | Financials | enabler | 2 |
| HK | `HK.LIST1030` | Investment & Asset Management | Financials | enabler | 2 |
| HK | `HK.LIST1007` | Other Financial Services | Financials | cross_chain | 2 |
| HK | `HK.LIST23362` | Payment services | Financials | enabler | 2 |
| HK | `HK.LIST1311` | REITs | Financials | cross_chain | 2 |
| HK | `HK.LIST1068` | Securities & Brokerage | Financials | enabler | 2 |
| HK | `HK.LIST1086` | Medical Services | Healthcare | cross_chain | 2 |
| HK | `HK.LIST1357` | Pharmaceutical Distribution | Healthcare | cross_chain | 2 |
| HK | `HK.LIST1284` | Traditional Chinese Medicine | Healthcare | cross_chain | 2 |
| HK | `HK.LIST1063` | Aerospace & Defense | Industrials & Manufacturing | cross_chain | 2 |
| HK | `HK.LIST1041` | Auto Parts | Industrials & Manufacturing | cross_chain | 2 |
| HK | `HK.LIST1017` | Commercial Vehicles | Industrials & Manufacturing | cross_chain | 2 |
| HK | `HK.LIST1075` | Steel | Materials | cross_chain | 2 |
| HK | `HK.LIST1026` | Advertising Agencies | Media & Entertainment | enabler | 2 |
| HK | `HK.LIST1027` | Broadcasting | Media & Entertainment | cross_chain | 2 |
| HK | `HK.LIST1009` | publishing | Media & Entertainment | cross_chain | 2 |
| HK | `HK.LIST1040` | Automobiles | Other / Cross-sector | cross_chain | 2 |
| HK | `HK.LIST1061` | Conglomerates | Other / Cross-sector | cross_chain | 2 |
| HK | `HK.LIST23847` | Motorcycles and others | Other / Cross-sector | cross_chain | 2 |
| HK | `HK.LIST1268` | Other Clothing Accessories | Other / Cross-sector | cross_chain | 2 |
| HK | `HK.LIST1031` | Other Support Services | Other / Cross-sector | enabler | 2 |
| HK | `HK.LIST1014` | Satellite & Wireless Services | Other / Cross-sector | cross_chain | 2 |
| HK | `HK.LIST1035` | Textiles & Fabrics | Other / Cross-sector | cross_chain | 2 |
| HK | `HK.LIST23849` | dietary supplements | Other / Cross-sector | cross_chain | 2 |
| HK | `HK.LIST1091` | education | Other / Cross-sector | cross_chain | 2 |
| HK | `HK.LIST23848` | household consumables | Other / Cross-sector | cross_chain | 2 |
| HK | `HK.LIST1073` | Heavy Infrastructure | Real Estate & Infrastructure | cross_chain | 2 |
| HK | `HK.LIST1090` | Property Services & Management | Real Estate & Infrastructure | cross_chain | 2 |
| HK | `HK.LIST1019` | Real Estate Developers | Real Estate & Infrastructure | cross_chain | 2 |
| HK | `HK.LIST1020` | Real Estate Investment | Real Estate & Infrastructure | cross_chain | 2 |
| HK | `HK.LIST1089` | Real Estate Services | Real Estate & Infrastructure | cross_chain | 2 |
| HK | `HK.LIST23363` | Digital Solution Services | Technology & Telecom | enabler | 2 |
| HK | `HK.LIST1029` | Entertainment | Technology & Telecom | cross_chain | 2 |
| HK | `HK.LIST1002` | Procurement & Supply Chain Management | Technology & Telecom | cross_chain | 2 |
| HK | `HK.LIST1054` | Telecom Services | Technology & Telecom | cross_chain | 2 |
| HK | `HK.LIST23851` | Telecommunication network infrastructure | Technology & Telecom | cross_chain | 2 |
| HK | `HK.LIST1064` | Airlines | Transportation & Logistics | cross_chain | 2 |
| HK | `HK.LIST1076` | Railroads & Highways | Transportation & Logistics | cross_chain | 2 |
| HK | `HK.LIST1066` | Shipping & Ports | Transportation & Logistics | cross_chain | 2 |
| HK | `HK.LIST1032` | Sports & Recreation Facilities | Transportation & Logistics | cross_chain | 2 |
| US | `US.LIST2010` | Agricultural Inputs | Agriculture & Food | upstream | 1 |
| US | `US.LIST2427` | Beverages - Brewers | Agriculture & Food | downstream | 1 |
| US | `US.LIST2459` | Beverages - Non-Alcoholic | Agriculture & Food | downstream | 1 |
| US | `US.LIST2464` | Beverages - Wineries & Distilleries | Agriculture & Food | downstream | 1 |
| US | `US.LIST2108` | Packaged Foods | Agriculture & Food | midstream | 1 |
| US | `US.LIST2494` | Apparel Retail | Consumer | downstream | 1 |
| US | `US.LIST2075` | Consumer Electronics | Consumer | downstream | 1 |
| US | `US.LIST2253` | Electronic Gaming & Multimedia | Consumer | downstream | 1 |
| US | `US.LIST2106` | Footwear & Accessories | Consumer | downstream | 1 |
| US | `US.LIST2460` | Home Improvement Retail | Consumer | downstream | 1 |
| US | `US.LIST2431` | Internet Retail | Consumer | downstream | 1 |
| US | `US.LIST2092` | Pharmaceutical Retailers | Consumer | downstream | 1 |
| US | `US.LIST2475` | REIT - Hotel & Motel | Consumer | downstream | 1 |
| US | `US.LIST2141` | REIT - Retail | Consumer | downstream | 1 |
| US | `US.LIST2046` | Resorts & Casinos | Consumer | downstream | 1 |
| US | `US.LIST2502` | Specialty Retail | Consumer | downstream | 1 |
| US | `US.LIST2498` | Travel Services | Consumer | downstream | 1 |
| US | `US.LIST2505` | Coking Coal | Energy & Utilities | upstream | 1 |
| US | `US.LIST2257` | Oil & Gas Equipment & Services | Energy & Utilities | midstream | 1 |
| US | `US.LIST2487` | Thermal Coal | Energy & Utilities | upstream | 1 |
| US | `US.LIST2489` | Utilities - Regulated Gas | Energy & Utilities | midstream | 1 |
| US | `US.LIST2461` | Utilities - Renewable | Energy & Utilities | midstream | 1 |
| US | `US.LIST2458` | Utilities - Regulated Water | Environmental Services | midstream | 1 |
| US | `US.LIST2069` | Biotechnology | Healthcare | midstream | 1 |
| US | `US.LIST2049` | Apparel Manufacturing | Industrials & Manufacturing | downstream | 1 |
| US | `US.LIST2468` | Auto Manufacturers | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2483` | Building Products & Equipment | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2509` | Business Equipment & Supplies | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2098` | Communication Equipment | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2428` | Drug Manufacturers - General | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2513` | Drug Manufacturers - Specialty & Generic | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2493` | Electrical Equipment & Parts | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2033` | Engineering & Construction | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2471` | Farm & Heavy Construction Machinery | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2237` | Packaging & Containers | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2005` | Residential Construction | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2016` | Semiconductor Equipment & Materials | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2463` | Specialty Industrial Machinery | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2499` | Textile Manufacturing | Industrials & Manufacturing | midstream | 1 |
| US | `US.LIST2211` | Aluminum | Materials | upstream | 1 |
| US | `US.LIST2020` | Chemicals | Materials | upstream | 1 |
| US | `US.LIST2510` | Copper | Materials | upstream | 1 |
| US | `US.LIST2110` | Gold | Materials | upstream | 1 |
| US | `US.LIST2270` | Metal Fabrication | Materials | upstream | 1 |
| US | `US.LIST2501` | Other Industrial Metals & Mining | Materials | upstream | 1 |
| US | `US.LIST2507` | Other Precious Metals & Mining | Materials | upstream | 1 |
| US | `US.LIST2083` | Paper & Paper Products | Materials | upstream | 1 |
| US | `US.LIST2068` | Specialty Chemicals | Materials | upstream | 1 |
| US | `US.LIST2488` | Utilities - Diversified | Other / Cross-sector | midstream | 1 |
| US | `US.LIST2462` | Utilities - Independent Power Producers | Other / Cross-sector | midstream | 1 |
| US | `US.LIST2472` | Utilities - Regulated Electric | Other / Cross-sector | midstream | 1 |
| US | `US.LIST2072` | Electronic Components | Technology & Telecom | midstream | 1 |
| US | `US.LIST2015` | Semiconductors | Technology & Telecom | midstream | 1 |
| US | `US.LIST2470` | Software - Application | Technology & Telecom | midstream | 1 |
| US | `US.LIST2508` | Software - Infrastructure | Technology & Telecom | midstream | 1 |
| US | `US.LIST2500` | Integrated Freight & Logistics | Transportation & Logistics | midstream | 1 |
| US | `US.LIST2478` | Food Distribution | Agriculture & Food | cross_chain | 2 |
| US | `US.LIST2264` | Tobacco | Agriculture & Food | cross_chain | 2 |
| US | `US.LIST2063` | Leisure | Consumer | cross_chain | 2 |
| US | `US.LIST2274` | Oil & Gas Drilling | Energy & Utilities | cross_chain | 2 |
| US | `US.LIST2058` | Oil & Gas E&P | Energy & Utilities | cross_chain | 2 |
| US | `US.LIST2224` | Oil & Gas Integrated | Energy & Utilities | cross_chain | 2 |
| US | `US.LIST2226` | Oil & Gas Midstream | Energy & Utilities | cross_chain | 2 |
| US | `US.LIST2060` | Oil & Gas Refining & Marketing | Energy & Utilities | cross_chain | 2 |
| US | `US.LIST2047` | Solar | Energy & Utilities | cross_chain | 2 |
| US | `US.LIST2219` | Waste Management | Environmental Services | cross_chain | 2 |
| US | `US.LIST2249` | Asset Management | Financials | enabler | 2 |
| US | `US.LIST2481` | Banks - Diversified | Financials | enabler | 2 |
| US | `US.LIST2456` | Banks - Regional | Financials | enabler | 2 |
| US | `US.LIST2261` | Credit Services | Financials | enabler | 2 |
| US | `US.LIST2495` | Financial Conglomerates | Financials | cross_chain | 2 |
| US | `US.LIST2490` | Financial Data & Stock Exchanges | Financials | cross_chain | 2 |
| US | `US.LIST2429` | Insurance - Diversified | Financials | enabler | 2 |
| US | `US.LIST2512` | Insurance - Life | Financials | enabler | 2 |
| US | `US.LIST2484` | Insurance - Property & Casualty | Financials | enabler | 2 |
| US | `US.LIST2467` | Insurance - Reinsurance | Financials | enabler | 2 |
| US | `US.LIST2465` | Insurance - Specialty | Financials | enabler | 2 |
| US | `US.LIST2230` | Insurance Brokers | Financials | enabler | 2 |
| US | `US.LIST2145` | REIT - Diversified | Financials | cross_chain | 2 |
| US | `US.LIST2469` | REIT - Mortgage | Financials | cross_chain | 2 |
| US | `US.LIST2457` | REIT - Office | Financials | cross_chain | 2 |
| US | `US.LIST2140` | REIT - Residential | Financials | cross_chain | 2 |
| US | `US.LIST2482` | REIT - Specialty | Financials | cross_chain | 2 |
| US | `US.LIST2011` | Diagnostics & Research | Healthcare | cross_chain | 2 |
| US | `US.LIST2262` | Health Information Services | Healthcare | cross_chain | 2 |
| US | `US.LIST2246` | Healthcare Plans | Healthcare | cross_chain | 2 |
| US | `US.LIST2486` | Medical Care Facilities | Healthcare | cross_chain | 2 |
| US | `US.LIST2280` | Medical Devices | Healthcare | cross_chain | 2 |
| US | `US.LIST2220` | Medical Distribution | Healthcare | cross_chain | 2 |
| US | `US.LIST2014` | Medical Instruments & Supplies | Healthcare | cross_chain | 2 |
| US | `US.LIST2503` | REIT - Healthcare Facilities | Healthcare | cross_chain | 2 |
| US | `US.LIST2089` | Aerospace & Defense | Industrials & Manufacturing | cross_chain | 2 |
| US | `US.LIST2055` | Auto Parts | Industrials & Manufacturing | cross_chain | 2 |
| US | `US.LIST2245` | Industrial Distribution | Industrials & Manufacturing | cross_chain | 2 |
| US | `US.LIST2466` | REIT - Industrial | Industrials & Manufacturing | cross_chain | 2 |
| US | `US.LIST2214` | Recreational Vehicles | Industrials & Manufacturing | cross_chain | 2 |
| US | `US.LIST2101` | Steel | Materials | cross_chain | 2 |
| US | `US.LIST2030` | Advertising Agencies | Media & Entertainment | enabler | 2 |
| US | `US.LIST2497` | Broadcasting | Media & Entertainment | cross_chain | 2 |
| US | `US.LIST2008` | Publishing | Media & Entertainment | cross_chain | 2 |
| US | `US.LIST2256` | Auto & Truck Dealerships | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2260` | Capital Markets | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2473` | Confectioners | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2216` | Conglomerates | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2476` | Consulting Services | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2080` | Department Stores | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2240` | Discount Stores | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2007` | Farm Products | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2426` | Furnishings, Fixtures & Appliances | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2094` | Gambling | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2095` | Grocery Stores | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2003` | Household & Personal Products | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2252` | Information Technology Services | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2263` | Lodging | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2052` | Lumber & Wood Production | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2276` | Luxury Goods | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2479` | Mortgage Finance | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2203` | Personal Services | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2227` | Pollution & Treatment Controls | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2273` | Rental & Leasing Services | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2225` | Restaurants | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2275` | Scientific & Technical Instruments | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2268` | Security & Protection Services | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2504` | Shell Companies | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2093` | Silver | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2474` | Specialty Business Services | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2496` | Staffing & Employment Services | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2243` | Tools & Accessories | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2267` | Trucking | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2430` | Uranium | Other / Cross-sector | cross_chain | 2 |
| US | `US.LIST2034` | Building Materials | Real Estate & Infrastructure | cross_chain | 2 |
| US | `US.LIST2477` | Infrastructure Operations | Real Estate & Infrastructure | cross_chain | 2 |
| US | `US.LIST2511` | Real Estate - Development | Real Estate & Infrastructure | cross_chain | 2 |
| US | `US.LIST2480` | Real Estate - Diversified | Real Estate & Infrastructure | cross_chain | 2 |
| US | `US.LIST2038` | Real Estate Services | Real Estate & Infrastructure | cross_chain | 2 |
| US | `US.LIST2492` | Computer Hardware | Technology & Telecom | cross_chain | 2 |
| US | `US.LIST2044` | Education & Training Services | Technology & Telecom | cross_chain | 2 |
| US | `US.LIST2506` | Electronics & Computer Distribution | Technology & Telecom | cross_chain | 2 |
| US | `US.LIST2491` | Entertainment | Technology & Telecom | cross_chain | 2 |
| US | `US.LIST2004` | Internet Content & Information | Technology & Telecom | cross_chain | 2 |
| US | `US.LIST2088` | Telecom Services | Technology & Telecom | cross_chain | 2 |
| US | `US.LIST2090` | Airlines | Transportation & Logistics | cross_chain | 2 |
| US | `US.LIST2234` | Airports & Air Services | Transportation & Logistics | cross_chain | 2 |
| US | `US.LIST2485` | Marine Shipping | Transportation & Logistics | cross_chain | 2 |
| US | `US.LIST2102` | Railroads | Transportation & Logistics | cross_chain | 2 |

## Graph Model

The graph starts with plate-level nodes and heuristic edges. Use it as a research queue, not as a factual supplier contract map. Report writers should replace heuristic edges with sourced company-specific evidence when producing a brief.

| File | Purpose |
| --- | --- |
| `data/sector-universe/moomoo_hk_us_plates.json` | Raw Moomoo plate taxonomy. |
| `data/sector-universe/moomoo_hk_us_plates.csv` | Spreadsheet-friendly plate list. |
| `data/sector-universe/value_chain_nodes.csv` | Graph nodes with domain and role labels. |
| `data/sector-universe/value_chain_edges.csv` | Starter graph edges for upstream/midstream/downstream analysis. |
| `data/sector-universe/value_chain_graph.mmd` | Mermaid graph preview for docs. |

Current graph size: `643` nodes, `53` starter edges.

## Research Use

1. Pick a priority industry plate from this document.
2. Expand constituents with Moomoo `get_plate_stock(plate_code)`.
3. Assign companies to upstream, midstream, downstream, or enabler roles.
4. Replace heuristic graph edges with sourced evidence: customer/supplier disclosure, revenue segment exposure, commodity input sensitivity, distribution channel, or regulatory linkage.
5. Feed the selected market/industry into the scheduled sector brief rotation.
