"""Active P1-only training entry; historical P0 experiments are retired."""
from models.ecr_mwm.p1_training import (main, run, fit_one, reload_model,
                                       checkpoint_bytes, seed_everything)

if __name__ == '__main__':
    main()
