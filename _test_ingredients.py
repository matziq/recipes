from build import extract_ingredients_from_html

samples = {
    "Florentine": '<p><strong>Florentine</strong></p><table><tr><td><p>1 (10 ounce) package frozen chopped spinach - thawed, drained and squeezed dry</p></td></tr><tr><td><p>1 (14 ounce) can artichoke hearts, drained and chopped</p></td></tr><tr><td><p>3 cloves garlic, minced</p></td></tr><tr><td><p>1/2 cup mayonnaise</p></td></tr><tr><td><p>2 (8 ounce) packages cream cheese, softened</p></td></tr><tr><td><p>2 tablespoons lemon juice</p></td></tr><tr><td><p>1 cup grated Parmesan cheese</p></td></tr></table>',
    "Guac": '<p>1 large ripe avocado, peeled and pitted <br />2 teaspoons fresh lime juice <br />1/2 cup fresh cilantro, chopped <br />2 large cloves garlic, finely chopped <br />2 large Serrano chilies, seeded and chopped <br />1/4 teaspoon salt</p>',
    "Dates": '<h3>Algerian Stuffed Dates</h3><p>24  Medjool dates (about 1 pound)<br />2  drops green food coloring (optional)<br />2/3  cup marzipan (almond paste)<br />2  teaspoons powdered sugar</p>',
    "Crunchwrap": '<h2>Ingredients</h2><ul><li>5 large flour tortillas (10-inch)</li><li>1 pound lean ground beef</li><li>1/3 cup water</li><li>1 ounce taco seasoning</li><li>2/3 cup nacho cheese sauce</li><li>4 tostada shells</li><li>2/3 cup sour cream</li><li>1 cup shredded iceberg lettuce</li><li>1 cup diced fresh tomatoes</li><li>2 cups shredded Mexican cheese blend</li></ul><h2>Instructions</h2><ol><li>In a large skillet, cook ground beef</li></ol>',
    "Sub": '<p>1 cup lard, substitute avocado oil<br />2 cups flour<br />1 tsp salt</p>',
}
for name, body in samples.items():
    print(name, "->", extract_ingredients_from_html(body))
