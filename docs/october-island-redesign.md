# October island itinerary redesign

The SVG map uses a shared equirectangular projection for Natural Earth land geometry,
place anchors, schematic route segments and character animation. It is NOT a road
router or GPS tracker. Unknown places have no invented coordinate or connecting line.
A hotel's user-supplied coordinates are saved in `trip.plan.hotel`; repeated visits
share one landmark. The old template remains available for saved-plan references.
The new recommendation is opt-in for saved plans, with undo.

## Sources checked 2026-09-25
- Coast: Natural Earth 1:10m land, public domain.
  https://www.naturalearthdata.com/about/terms-of-use/
  Input: https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson
- UMI shisa pair painting, 90–120 minutes, same-day take-home:
  https://en.umi.okinawa.jp/course/si-sa/
  https://en.umi.okinawa.jp/access/
- SAM'S Anchor Inn Ginowan, teppanyaki, dinner hours and booking:
  https://sams-ancaor-inn-ginowan.com/en_us/
- Kafu Seragaki, shabu-shabu, address, dinner hours and booking:
  https://www.kafu-onna.com/shop/seragaki.html

Coordinates for the three new businesses come from the centers of their official
embedded location maps. They are approximate display anchors, not surveyed entrances.
Other coordinates are inherited from the project. Unverified prices stay unknown.

## Artwork
`web/assets/trip/landmarks.webp` is a transparent 3×3 atlas created with the built-in
image generation tool. Each cell is independently rendered in SVG. These are symbolic
miniatures, not photographs of the actual places. Existing couple sprite retained.
`map-preview.svg` is an application preview composed from the coast and atlas.

Generation prompt: ONE transparent game sprite atlas, 3 columns × 3 rows, isometric
miniature Okinawa landmarks in a coherent detailed painted 3D style. Row 1: whale-shark
aquarium, Kouri bridge/island, colorful American Village without ferris wheel. Row 2:
shisa pair with craft studio, white stepped Umikaji terrace, resort hotel. Row 3:
red-tile soba restaurant, Naha shopping street, airport terminal and airplane.
No text, grid or people; independent transparent cells with margins.

## Verification
`npm test`, `python tests/test_deploy.py`, `python tests/test_trip_hub.py`.
New DOM scenarios cover opt-in/undo, final-day alternatives, hotel persistence and
single-landmark revisits, projection direction, animation pause/resume, no GPS/visit
completion side effects. Original scenarios use an explicit legacy fixture.
