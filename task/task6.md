Using the MiniShop Master Prompt and existing Shop system, implement geographic location support using PostgreSQL + PostGIS.

Requirements:

1. Configure PostGIS.
2. Add geographic PointField to Shop.
3. Store longitude/latitude correctly.
4. Validate coordinates.
5. Add location update API.
6. Support nearby shop search.
7. Support radius in kilometers.
8. Calculate distance.
9. Sort by nearest distance.
10. Optimize the database query with an appropriate spatial index.

Example:

GET /api/shops/nearby/?lat=23.8103&lng=90.4125&radius=2

Expected behavior:

* Search shops within 2 km.
* Return distance.
* Sort nearest first.
* Do not return inactive/suspended shops.
* Validate radius.
* Prevent unauthorized seller location modification.

Also design the API so it can later support:

* nearby products
* category filtering
* shop filtering
* pagination

Add backend tests for:

* valid coordinates
* invalid coordinates
* radius search
* shops inside radius
* shops outside radius
* inactive shop exclusion
* distance ordering
