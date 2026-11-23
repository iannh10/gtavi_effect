"""Model specifications for the exploratory bake-off. Fixed in PLAN.md before any result existed.

Monthly: 3 candidate configs per model (A, B, C). One is chosen per model and target using only
control-unit errors at tuning origins (<= 2024-08). Daily: one fixed config (D) per model, no tuning.
"""

MODELS = ["nbeats", "nhits", "gru", "lstm", "patchtst", "tft"]   # also the complexity order for the all-in selection

# Settings shared by every model and config. No validation set and no early stopping: a fixed step budget.
COMMON = dict(loss="MAE", scaler_type="robust", learning_rate=1e-3, batch_size=32, windows_batch_size=128,
              val_check_steps=10_000, early_stop_patience_steps=-1)

STEPS = {"monthly": 500, "daily": 300}

MONTHLY = {
    "lstm": {
        "A": dict(input_size=24, encoder_n_layers=1, encoder_hidden_size=32, decoder_hidden_size=32),
        "B": dict(input_size=24, encoder_n_layers=2, encoder_hidden_size=64, decoder_hidden_size=64),
        "C": dict(input_size=12, encoder_n_layers=2, encoder_hidden_size=64, decoder_hidden_size=64),
    },
    "gru": {
        "A": dict(input_size=24, encoder_n_layers=1, encoder_hidden_size=32, decoder_hidden_size=32),
        "B": dict(input_size=24, encoder_n_layers=2, encoder_hidden_size=64, decoder_hidden_size=64),
        "C": dict(input_size=12, encoder_n_layers=2, encoder_hidden_size=64, decoder_hidden_size=64),
    },
    "nbeats": {
        "A": dict(input_size=24, mlp_units=[[128, 128], [128, 128], [128, 128]]),
        "B": dict(input_size=24, mlp_units=[[256, 256], [256, 256], [256, 256]]),
        "C": dict(input_size=12, mlp_units=[[256, 256], [256, 256], [256, 256]]),
    },
    "nhits": {
        "A": dict(input_size=24, mlp_units=[[128, 128], [128, 128], [128, 128]], n_pool_kernel_size=[2, 2, 1], n_freq_downsample=[2, 1, 1]),
        "B": dict(input_size=24, mlp_units=[[256, 256], [256, 256], [256, 256]], n_pool_kernel_size=[2, 2, 1], n_freq_downsample=[2, 1, 1]),
        "C": dict(input_size=12, mlp_units=[[256, 256], [256, 256], [256, 256]], n_pool_kernel_size=[2, 1, 1], n_freq_downsample=[2, 1, 1]),
    },
    "tft": {
        "A": dict(input_size=24, hidden_size=16, n_head=2),
        "B": dict(input_size=24, hidden_size=32, n_head=4),
        "C": dict(input_size=12, hidden_size=32, n_head=4),
    },
    "patchtst": {
        "A": dict(input_size=24, patch_len=6, stride=3, hidden_size=32, n_heads=4, encoder_layers=2, linear_hidden_size=64),
        "B": dict(input_size=24, patch_len=6, stride=3, hidden_size=64, n_heads=4, encoder_layers=3, linear_hidden_size=128),
        "C": dict(input_size=12, patch_len=4, stride=2, hidden_size=64, n_heads=4, encoder_layers=3, linear_hidden_size=128),
    },
}

# Daily: neuralforecast-style defaults scaled to 14 lags (the frozen MLP's daily_lags), never tuned.
DAILY = {
    "lstm": {"D": dict(input_size=14, encoder_n_layers=2, encoder_hidden_size=64, decoder_hidden_size=64)},
    "gru": {"D": dict(input_size=14, encoder_n_layers=2, encoder_hidden_size=64, decoder_hidden_size=64)},
    "nbeats": {"D": dict(input_size=14, mlp_units=[[256, 256], [256, 256], [256, 256]])},
    "nhits": {"D": dict(input_size=14, mlp_units=[[256, 256], [256, 256], [256, 256]], n_pool_kernel_size=[2, 2, 1], n_freq_downsample=[4, 2, 1])},
    "tft": {"D": dict(input_size=14, hidden_size=32, n_head=4)},
    "patchtst": {"D": dict(input_size=14, patch_len=7, stride=3, hidden_size=64, n_heads=4, encoder_layers=3, linear_hidden_size=128)},
}

# Rolling-origin schedule. A model is refitted every `refit_every` origins (anchored on the first backtest origin)
# and, between refits, forecasts from each origin with the newest data as input and no weight update.
REFIT_EVERY = {"monthly": 6, "daily": 1}   # monthly refits fall on Octobers and Aprils
TUNING_LAST_ORIGIN = "2024-08"          # 24 months before the last monthly backtest origin (2026-08)
SEEDS = 3                               # seeds = config seed + 0, 1, 2; the forecast is the mean over seeds
CONFIG_ORDER = ["A", "B", "C"]         # tie-break order when tuning scores are equal
TUNING_UNITS = "controls"               # tuning is scored on the 18 controls only; GTA V never enters it
