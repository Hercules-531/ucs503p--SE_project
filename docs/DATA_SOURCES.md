# Phase-one data-source register

Checked on **9 September 2026**. The application stores small, manually curated snapshots; it does not copy entire datasets or call these services live.

| Prototype records | Publisher/source | URL | Use in Phase 1 |
| --- | --- | --- | --- |
| PM-KISAN, AB PM-JAY, PMAY-U, PMUY, PM SVANidhi, DHTESS, JSY | myScheme, Digital India Corporation | <https://www.myscheme.gov.in/> | Names, responsible organisation, broad purpose and source links. |
| Atal Pension Yojana | Pension Fund Regulatory and Development Authority | <https://pfrda.org.in/web/pfrda/schemes/atal-pension-yojana-apy> | Broad purpose, target audience and source link. |
| PIN-code examples | OGD Platform India, Department of Posts | <https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month> | Three demonstration location records. |

## Data-use rules

- Only stable summary fields are shown; detailed eligibility and benefit amounts are deliberately omitted.
- Each record carries a source URL and `last_verified` date.
- The portal says “potentially relevant,” not “eligible.”
- Users are directed to the official source before applying or acting.
- No citizen answers, identity numbers or personal profiles are stored.
- Restricted sources and identity-verification services are outside project scope.

## Department of Posts PIN directory import

The [OGD catalogue](https://data.gov.in/catalog/all-india-pincode-directory-through-webservice)
identifies the PIN directory as open access and describes office, PIN, district and state fields.
The [resource page](https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month)
identifies the Department of Posts as the publisher. The platform identifies its published data as
subject to the [Government Open Data License - India](https://data.gov.in/Godl), which requires
attribution and contains further conditions. Review the dataset's current terms before reuse.

The optional CSV adapter imports a file obtained separately from that official resource page; it
does not download the data itself or authenticate to the API. The operator must verify the file,
its provenance and date. The adapter retains the provider, resource URL and licence on each record,
groups all offices under each PIN and rejects the entire batch if a required row is malformed.
`office_name`, `district` and `state` represent the first sorted office for compatibility; the
`offices` array contains all offices in the imported file for that PIN. Imports upsert PINs. Prior
records owned by this adapter but absent from a later file are retained and marked for review,
not deleted; a partial file can cause omitted records to be marked for review. No official CSV
has been bundled.

On 5 November 2026, the resource page published the expected headers `officename`, `pincode`,
`district` and `statename`, but its linked CSV returned HTTP 403 when requested. No downloaded
snapshot was verified or imported during this check; the adapter tests use synthetic fixtures.
An optional `scripts.fetch_ogd_pincode` downloader accepts an operator-supplied resource UUID and
API key for the official API host and writes a new CSV for review. It has only been tested with
simulated responses, not the live PIN API. Stable reported totals do not prove that offset pages
formed a consistent snapshot, nor that the supplied UUID is the PIN resource. The operator must
independently verify resource identity, completeness, date and terms before import.
The OGD platform's [help page](https://data.gov.in/help) describes API-key generation for
registered users. No user API key has been requested or stored by this project. A locally
downloaded, independently verified CSV remains an alternative for the existing adapter.

On 23 November 2026, the [OGD resource listing](https://data.gov.in/resource/all-india-pincode-directory-till-last-month)
identified the resource UUID as `5c2f62fe-5afa-4119-a499-fec9d604d5bd`. The listed public CSV link
returned HTTP 403 again. The [IndiaAI AIKosh listing](https://aikosh.indiaai.gov.in/home/datasets/details/all_india_pincode_directory_till_last_month_1.html)
points to that same OGD resource. A full official file remains unavailable in this environment.
The PIN adapters now store the SHA-256 of each newly imported file with the record provenance.
The manual official importer can match it against an operator-reviewed digest.
When trimming changes a PIN, office, district or state value, the office keeps the original text
under `original_values`. Equivalent office entries still share one normalized office record.

### Historical third-party mirror

On 14 November 2026 a 2024 [GitHub mirror](https://github.com/dropdevrahul/pincodes-india)
was downloaded because the official download was unavailable. The repository claims the data
originated from the OGD directory, but the bytes have not been independently compared with the
government file. The dedicated mirror adapter pins the file checksum and keeps the mirror URL,
claimed original URL and repository licence in every record. The mirror commit date is stored as
`snapshot_date`, not as an official verification date; `last_verified` is null. All imported records remain `review_due` with reason
`unverified_mirror`. Do not use this snapshot to claim current postal availability. The raw CSV
and its local provenance note are excluded from Git by the `data/raw/` ignore rule.
For matching PINs, the mirror adapter preserves records owned by other adapters or with unknown
ownership. It updates only its own prior records and reports the count actually applied.

## PIB JanSamarth scheme snapshot

The [Ministry of Finance release published by PIB on 30 March 2026](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2247026&lang=2&reg=3)
lists 15 credit-linked schemes. The adapter imports 14 names and ministries from that table,
omitting PM SVANidhi because it is already in the default catalogue. PIB's [copyright policy](https://www.pib.gov.in/content/3604_2_CopyrightPolicy.aspx?lang=1&reg=6)
permits reproduction subject to accurate, non-misleading use and attribution, with third-party
material excluded. The snapshot includes the publisher, release and policy URLs.

The release is historical, not a live dataset. Records use the release date as a conservative
verification date and are explicitly marked `review_due`; current availability, geographic scope,
eligibility and benefits must be checked independently. Categories and tags are local discovery
labels, while states and audiences are left empty when the table does not establish them. The
adapter performs no live scraping and does not claim complete coverage of the 15 schemes.

## PIB transport snapshot

The [28 July 2026 Ministry of Heavy Industries release](https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=2290696&lang=2&reg=48)
describes PM E-DRIVE's electric mobility and charging objectives and records different dates for
individual vehicle segments. BharatOS transcribes one broad description, labels it `review_due`,
and leaves state and audience fields unspecified. The publication date is used as a conservative
verification date; the record does not establish present availability or eligibility. The same
PIB copyright policy linked above applies. This is a manually curated historical snapshot, not a
live feed or a complete transport dataset.

## PIB environment snapshot

The [30 July 2026 Ministry of Environment, Forest and Climate Change release](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2291891&lang=1&reg=6)
describes National Clean Air Programme action plans in 130 cities. The record is a dated,
manually curated programme summary, marked `review_due` and not a live coverage list. The source
does not describe an individual payment or application process. States and audiences are left
unspecified rather than implying that every location is covered. PIB's policy above applies.

## PIB health, education, employment and agriculture snapshots

The linked releases were checked on 23 November 2026. These summaries retain the publication
date separately from the date the link and its contents were checked. Records remain
`review_due` because the releases describe past programme information. Audience tags support
discovery. Current eligibility, geographic availability and enrolment require confirmation
from the responsible authority.

| Records | Publisher and release |
| --- | --- |
| Pradhan Mantri National Dialysis Programme | [Ministry of Health and Family Welfare, 11 August 2026](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2297506&lang=2&reg=48) |
| Samagra Shiksha and NIPUN Bharat Mission | [Ministry of Education, 10 August 2026](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2297131&lang=1&reg=48) |
| Pradhan Mantri Viksit Bharat Rozgar Yojana | [Ministry of Labour and Employment, 19 June 2026](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2275419&lang=1&reg=1) |
| National Mission on Natural Farming | [Ministry of Agriculture and Farmers Welfare, 24 March 2026](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2244625&lang=2&reg=3) |

The project stores brief paraphrases with attribution and a link to the PIB copyright policy.
The importer runs entirely from the curated local snapshots.

The public scheme filter also lists the states and union territories from the
[Integrated Government Online Directory](https://igod.gov.in/sg/states). The presence of a region
in the selector does not establish programme coverage there. Matches still use the scope recorded
in each scheme snapshot.
