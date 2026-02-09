# number of different priority groups that can preempt each others
# on cortex-m0 there are priority configurable 2 bits, so 4 total priorities
# please note this does not apply to fixed exceptions like Reset/HardFault/etc.
PRIORITY_GROUPS = 4
