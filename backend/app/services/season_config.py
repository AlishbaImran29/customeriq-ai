"""Settings of the Season Forecast, in one place (the season dates are in app/data/seasons.json).

The minimum number of products a conclusion needs is NOT here: it is data_rules.MIN_GROUP_COUNT, the one
number shared by every feature (project rule 2).
"""

# The forecast is made this many days before the season window starts. The back-test uses exactly the
# same distance, so the scores describe the forecast that is actually shown.
HORIZON_DAYS = 28

# "Recent sales" for the model = units sold in the last this-many weeks before the forecast is made.
RECENT_WEEKS = 8

# The model must be at least this much better than the baseline (lower average error) on held-out
# seasons before its forecast is shown. 5% keeps luck from counting as skill.
MIN_IMPROVEMENT = 0.05

# The model needs at least this many earlier (product, season, year) rows to learn from.
MIN_TRAIN_ROWS = 40

# MAPE (percentage error) is undefined for a product that sold nothing, so only products that sold at
# least this many units in the season count towards it. MAE (average error in units) counts every product.
MIN_UNITS_FOR_MAPE = 5

# Advice labels compare the forecast with last year's sales of the same product.
STOCK_MORE_RATIO = 1.15
STOCK_LESS_RATIO = 0.85

# The range shown around a forecast covers the middle 80% of the model's past errors in the back-test.
RANGE_LOW_QUANTILE = 0.10
RANGE_HIGH_QUANTILE = 0.90

# How many products are listed per season.
MAX_LISTED_PRODUCTS = 50
