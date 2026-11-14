# Stage 2 — Site Catalogue

Data: [data/catalogue/sites.json](../../data/catalogue/sites.json) (tracked). Loader and policy enforcement: [engine/lunarnav/sites.py](../../engine/lunarnav/sites.py). Researched 2026-11-14.

## Coordinate convention (all records)
Planetocentric latitude, south negative; **east-positive** longitude; frame MOON_ME; reference sphere R = 1737.4 km. Custom input accepts lon in [-180, 360] and normalises to [-180, 180); other values are rejected (not wrapped).

## Curated sites (4)

| id | Kind | Lat (deg) | Lon E (deg) | Published height | Primary sources |
|---|---|---|---|---|---|
| `im1-odysseus` | **confirmed landing** (2024-02-22) | -80.12759 | 1.44587 | 2583 m (NAIF); 2579 m (LROC) | NAIF CLPS kernel `clps_to2im_im1_v02.tf`; LROC image page 1360 |
| `im2-athena` | **confirmed landing** (2025-03-06) | -84.79059 | 29.19567 | 5321 m (NAIF) | NAIF CLPS kernel `clps_prime1_im2_v01.tf`; LROC image page 1408 |
| `im2-intended` | **intended target** (pre-landing; not where the lander rests) | -84.78 | 29.13 | none | LROC image page 1401 |
| `chandrayaan3-shiv-shakti` | **confirmed landing** (2023-08-23) | -69.3741 | 32.32 | 532 m (LROC; datum not verified) | LROC image page 1314 |

Source URLs and verbatim quotes are stored per record. The NAIF kernels state the values as planetodetic coordinates on a reference spheroid with equatorial = polar radius = 1737.4 km in frame MOON_ME, so they equal planetocentric values on this sphere. Automated tests assert that every catalogue coordinate appears in its quoted source text and that NAIF-sourced values match the kernel text exactly.

## Deliberately excluded (decision C7)

| Item | Why not a site |
|---|---|
| NASA Artemis III candidate regions (Peak near Cabeus B, Haworth, Malapert Massif, Mons Mouton Plateau, Mons Mouton, Nobile Rim 1, Nobile Rim 2, de Gerlache Rim 2, Slater Plain; ~15 km regions) | Names and sizes are NASA-published, but no authoritative centre coordinates were found in a primary source. One secondary study quotes a point for Nobile Rim 2 and another page conflicts with it, so neither is used. Listed under `pending_regions`. |
| Luna 25 impact site | Not an intact landing; the LROC release was not located. |
| Mazarico et al. (2011) numbered sites (Site 01, 04, 07 ...) | PGDA names them for its 5 m products but publishes extents rather than a site coordinate that I could cite. |

Next step for Artemis regions: obtain the centres from NASA's Artemis III site-selection documents (NTRS 20250011660 and linked LPSC material) or LROC, then add them with `candidate_region` kind.

## Schema (site record)
`id, name, kind (confirmed_landing | intended_target | candidate_region | custom), lat_deg, lon_deg_east, lat_convention, lon_convention, reference_height_m?, reference_height_source?, notes, sources[{label, url (https), description, quote}]`. A catalogue entry without at least one source, with a `custom` kind, duplicate ids, a non-https URL, or a different coordinate convention makes loading (and API start-up) fail.

## Sample API record (`GET /sites`)
```json
{"id":"im2-athena","name":"IM-2 Athena landing site (Mons Mouton)","kind":"confirmed_landing",
 "lat_deg":-84.79059,"lon_deg_east":29.19567,"lat_convention":"planetocentric",
 "lon_convention":"east_positive","reference_height_m":5321.0,
 "sources":[{"label":"NAIF CLPS SPICE archive: IM-2 frame kernel","url":"https://naif.jpl.nasa.gov/...","quote":"Longitude (deg): 29.1956700000000; ..."}]}
```
## Custom coordinates
`POST /sites/validate {"lat": -89.5, "lon": 270}` returns a `custom` site with normalised longitude, an empty `sources` list, and the DEM coverage status (`covered`/`not_covered`). Coverage reflects only the locally extracted windows and never makes the coordinates invalid.
