ROUTES = "Routes"                       # Output routes feature class name
FIXED = "FixedAssets"                   # Output fixed assets feature class name
REMOTE = "RemoteAssets"                 # Output remote assets feature class name
NEAR_TABLE = "NearTable"                # Output near table table name
TEMP_GDB = "BackhaulAssets.gdb"         # temporary gdb name (unique name is generated from this)
FINAL_GDB = "BackhaulResults.gdb"       # final gdb name (unique name is generated from this)

NEAR_TABLE_SIZE = 50                    # Generate a near table with the nearest X assets. Set to None to find all.
MAX_SEARCH = 50                         # The maximum number of assets to add the the Closest Facility Solver.
MAX_DAISY = 10                          # The maximum number of assets to daisy chain.

COPY_ASSETS = True                      # Copy assets that were included in trace. If False: only save the results.
CREATE_RELATIONSHIPS = True             # Create relationships between routes and fixed/remote assets.
