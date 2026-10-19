"""Settings of the Order Risk Check, in one place so they are easy to find and to change.

Every number here is explained in the report; none of them is hidden inside the model code.
"""

# --- Labels ---------------------------------------------------------------------------
# A return can be reported weeks after the order. In Online Retail II half of the
# cancellations arrive within 9 days, 90% within 70 days and 95% within 125 days. An order
# newer than this many days (before the latest order in the data) may still be cancelled
# later, so its label is incomplete: it is NOT used to train or to test the model.
LABEL_MATURITY_DAYS = 90

# --- Train / test split (by time) -------------------------------------------------------
# The newest 25% of the orders with a complete label form the test set. The model is trained
# on orders that ended at least TRAIN_TEST_GAP_DAYS before the test period starts, so that at
# the split date every training label was already known (a real seller trains on today's
# knowledge, never on the future).
TEST_FRACTION = 0.25
TRAIN_TEST_GAP_DAYS = LABEL_MATURITY_DAYS

# --- The trust rule ---------------------------------------------------------------------
# The model is shown only if it beats the simple baseline ("the customer's own past cancel
# rate") on the TEST orders, and is good enough on its own.
TOP_FRACTION = 0.10         # precision is measured on the riskiest 10% of orders
MIN_AUC_MARGIN = 0.02       # the model's ROC-AUC must exceed the baseline's by at least this
MIN_MODEL_AUC = 0.60        # and must reach this on its own (0.5 means guessing)
MIN_TRAIN_ROWS = 300        # orders with a usable label in the training period
MIN_CLASS_ROWS = 30         # returned AND not-returned examples, in training and in testing

# --- Model ------------------------------------------------------------------------------
MAX_COUNTRIES = 5           # countries that get their own column; the rest share "other"
