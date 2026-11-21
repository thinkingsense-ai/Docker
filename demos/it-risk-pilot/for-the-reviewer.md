# Pilot sheets: what we are asking you to do

Thank you for looking at this. It takes about 30 to 45 minutes. Two spreadsheets, both CSV (they open in Excel or Numbers). You are giving us **your own judgement**, so please do not try to guess what our software would say: we have left its answers out on purpose.

## Sheet 1: `1-headlines.csv` (52 headlines)

Public headlines from the security and technology feeds we read. Some of them our software raised as "a possible story about AI-driven attack or weakness"; some it did not. **We are not telling you which**, so you are judging the headline, not our software. There is no article text (we do not store any): open the link if you need more.

In `leo_label`, write one of:

- `relevant`: a real story that bears on AI-driven attack or weakness **and** on a firm like a global bank.
- `not_for_us`: real, but not for a firm like that (for example a consumer product, or something outside financial services technology).
- `not_real`: not an incident (opinion, a promotion, a roundup, rumour).

Leave a row blank if you cannot tell, and say why in `leo_note` if you like. Blank rows are left out of the numbers and counted.

## Sheet 2: `2-systems.csv` (11 systems)

An **invented** firm's systems (no real organisation, nothing from a real estate). For each one, the facts we hold. In `leo_rating` write `Critical`, `High`, `Medium` or `Low`, for how bad a loss event on that system would be for the firm given what is shown:

- **Critical:** needs action now; a senior person should know today. **High:** needs action soon and a named owner. **Medium:** worth watching or fixing in the normal cycle. **Low:** little concern; record it.
- Please rate **inherent** risk (before controls), the way you would for a risk register. The facts include control evidence (patches, recovery tests) for you to weigh; we do not compute residual risk.
- In `leo_rank`, give your order for your top ten (1 is the system you would look at first). Leave the rest blank.

The columns: `tier` 1 (most critical) to 3; `dependents` how many other systems depend on it; `end_of_support` the vendor's date (blank if none announced); `open_patches`, `known_exploited_open` (open patches for flaws on a known-exploited list) and `max_epss_open` (the highest 0 to 1 exploit-likelihood score among open patches); `untested_changes` (recent changes that skipped pre-production testing); `days_since_test` and `recovery_result` (the last recovery test); `credentials_wide` (credentials visible beyond their owners or team); `in_scenario` (1 if it runs the technology involved in the November 2026 outages); `loss_event` (what a loss event would look like). The CVE numbers and every value are invented.

## How to send it back

Fill in `leo_label`, `leo_rating`, `leo_rank` and (optionally) `leo_note`. **Keep the `id` column exactly as it is** and save both files as CSV with the same names. Please do not add or delete rows.

## What happens next

We count how often your judgement matches what our rules did, with intervals (the samples are small, so we will say so), and for the systems how well your top ten matches ours, with precision and recall for Critical and High. **There is no pass mark and no target.** Where you disagree with the software is the useful part, so a note on why is worth more than a label.

These sheets are for you only; please do not pass them on.
