param(
    [string]$Table = "STOCK_DATA_KR",
    [string]$StartDate = "",
    [string]$EndDate = "",
    [double]$ValRatio = 0.2,
    [int]$SeqLen = 60,
    [int]$HorizonDays = 5,
    [double]$RiseThreshold = 0.10
)

$ErrorActionPreference = "Stop"

@'
import function.static as static
from model_kr import load_codes, compute_feature_stats, get_cutoff_date, WindowIterableDataset

table = "{TABLE}"
start = "{START_DATE}" or static.start_date
end = "{END_DATE}" or static.end_date
val_ratio = {VAL_RATIO}
seq_len = {SEQ_LEN}
horizon = {HORIZON_DAYS}
rise = {RISE_THRESHOLD}

codes = load_codes(table, start, end)
cutoff = get_cutoff_date(table, start, end, val_ratio)
mean, std = compute_feature_stats(table, start, end, cutoff)

ds = WindowIterableDataset(
    table, codes, start, end,
    seq_len, horizon, rise,
    cutoff, "train", mean, std,
    log_codes=False, log_every=999999
)

pos = neg = 0
for _, y in ds:
    if y.item() >= 0.5:
        pos += 1
    else:
        neg += 1

print("pos:", pos, "neg:", neg, "pos_weight:", neg / max(pos, 1))
'@.Replace("{TABLE}", $Table).
    Replace("{START_DATE}", $StartDate).
    Replace("{END_DATE}", $EndDate).
    Replace("{VAL_RATIO}", $ValRatio).
    Replace("{SEQ_LEN}", $SeqLen).
    Replace("{HORIZON_DAYS}", $HorizonDays).
    Replace("{RISE_THRESHOLD}", $RiseThreshold) | python -
