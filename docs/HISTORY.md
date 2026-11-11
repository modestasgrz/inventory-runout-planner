# Project history

This file explains how the app got to its current state and how to carry on with it, for someone who has no other context. The spec (`specs/inventory-runout-planner.md`) is the contract. This file records why things are the way they are. All dates are 2026.

## 1. Current state

| What | State |
| --- | --- |
| Shipped | Five pages (Overview, Forecast, Scenarios, Reorder plan, Methodology), a sidebar with scenario inputs, 5 presets plus Custom and Reset, 4 CSV exports, Graphite dark theme. The owner approved this version for the portfolio on 10 Nov. |
| Spec | `Status: approved (Change 5)`, 52 acceptance criteria (AC-01 to AC-52), 23 locked decisions (DEC-01 to DEC-23), no open questions |
| Main | Change 5 merged (PRs #22, #23, #24) plus the gate 5 screenshots (#25) |
| Live URL | _Not deployed yet. The Streamlit Community Cloud deploy is a pending owner step. Add the URL here once it exists._ |
| Data | Real monthly demand for 36 products (UCI Online Retail II, Dec 2009 – Nov 2011, CC BY 4.0). Stock, lead times, MOQ, unit cost, capacity and inbound orders are synthetic (seed 42). The planning date is fixed at 1 Dec 2011. |
| Runtime | No LLM, no API calls and nothing outbound at runtime |

| Test layer | Where | Count |
| --- | --- | --- |
| Acceptance (one per AC; only the spec owner edits them) | `tests/acceptance/inventory-runout-planner/` | 52 |
| PART-A unit and property tests (core) | `tests/inventory-runout-planner/part-a/` | 781 |
| PART-B AppTest checks (UI) | `tests/inventory-runout-planner/part-b/` | 379 |
| `make check` total (unit tests, without acceptance) | | 1 160 |

| Task | Command |
| --- | --- |
| Install | `uv sync` |
| Run the app | `make run` (http://127.0.0.1:8786) |
| Lint, types, security scans, unit tests | `make check` |
| Unit tests only | `make test` |
| Acceptance tests | `uv run pytest tests/acceptance` |
| One part's acceptance tests | `python3 scripts/agent_guardrails.py run --feature inventory-runout-planner --part PART-A` (or `PART-B`) |
| Rebuild the data | `uv run python scripts/build_data.py` (downloads about 45 MB and checks its SHA-256; `git status` must stay clean afterwards) |
| Screenshots | Restart `make run` from current main, then run `uv run python tools/screenshots.py [base_url]`. It writes 18 PNGs to `docs/screenshots/` (5 pages and 4 preset Overviews, at 1280 and 1440 px). |
| Streamlit Cloud requirements | `make requirements` (exports `requirements.txt` from `uv.lock`) |

Headline numbers (Baseline: £350 000 budget, 12 months, 1 month of safety stock):
- **At risk:** 10 of 36 products.
- **Spend:** £349 968 funded of £350 000.
- **Unfunded:** 24 orders (£74 620).
- **Lost sales:** £29 145 with the plan, against £560 063 if nothing is ordered.
- **Forecast error:** 61 % WAPE (seasonal method).

The README has the full preset table.

## 2. Decision log

The **Reversed?** column says whether a later decision replaced this one.

| Date | Decision | Why | Reversed? |
| --- | --- | --- | --- |
| 09 Nov | Real 2011 dates; top 36 products by units, with sales in ≥ 22 of 24 months; 4 groups from description keywords | Real public demand with no customer data; enough history for a seasonal forecast | No |
| 09 Nov | Seasonal naive forecast by default (same month last year × growth), with a trailing 3-month average as the alternative | Simple and traceable by hand; statistical models are out of scope | No |
| 09 Nov | Money in GBP; U+202F thin space as the thousands separator; units always shown | Matches the UK data and keeps numbers readable | No |
| 09 Nov | Product shown description first, code second (DEC-18); number inputs without step arrows (DEC-17) | Codes mean nothing to a reader; the steppers looked noisy | No |
| 09 Nov | Story products fixed in the synthetic data: 84347 (lead-time blocked), 85123A, 47566 (overstocked), 85099B (inbound order that a supplier delay breaks), 21212 (fine) | Each preset needs a visible, explainable effect | No |
| 09 Nov | Baseline budget £100 000 | Funded 81 % of the single next order per product | **Yes**, on 10 Nov (£350 000, see below) |
| 09 Nov | "At risk" = runs out within lead time + 1 month (Change 1, AC-35) | The first definition (any run-out in 12 months) hit 34 of 36 products, so the number told you nothing. The new one gave Baseline 7 and Delay 14. | **Yes**, on 10 Nov: at risk after the plan (DEC-19) |
| 09 Nov | `Custom` preset when any input is edited, and picking a preset reloads it (Change 2, AC-38); the `order_now` flag computed in the core (AC-39/40), not the UI | Edited inputs used to still show "Baseline"; UI and core disagreed on "order now" | No |
| 09 Nov | `requirements.txt` stays owner-only; a red spec-guard on PR #6 for it was accepted | Streamlit Cloud needs the file, and the kit marks it protected | No |
| 10 Nov | The repo was made public | CI minutes for private repos ran out and Actions stopped running. A privacy check came back clean before the switch: gitleaks found nothing, the authors are noreply, only aggregates are committed. | No |
| 10 Nov | Money KPIs: lost sales = unmet units × real median selling price; £ tied up for overstock (Change 3, DEC-19) | Reviewers asked for £ rather than units | No |
| 10 Nov | Lost sales after the plan counted only over the order's cover window (arrival + 2 months) | Whole horizon with a single order: £393 k after the plan against £560 k, almost no change. Cover window: £69 k (Tight £337 k, Efficiency £32 k), which looked more useful. | **Yes**, on 10 Nov (round 3): full horizon |
| 10 Nov | Products at risk = still short in some month **with** the plan | The KPI now moves with the budget | No |
| 10 Nov | Headline forecast error = weighted error (WAPE), labelled "weighted forecast error (WAPE)" | WAPE is 61 %. The plain mean of per-product MAPE is 171 %, inflated by months with almost no sales. Both appear on Methodology. | No |
| 10 Nov | Stock value removed from the KPI row; 5 KPI cards | Not a decision number | No |
| 10 Nov | "Urgency rank" kept as the ranking label | Clear enough for a buyer | No |
| 10 Nov | Lead-time flag group shown first, the other groups by £ (DEC-20) | Lead time is the only group that needs action today | No |
| 10 Nov | Headline lost sales = full horizon **with** the plan, with "if nothing ordered" as the sub-line (Change 4) | With the cover window, Efficiency looked better than Baseline while total loss rose. Reviewers called that misleading. | No (it replaces the cover window) |
| 10 Nov | Follow-up orders: up to 4 per product (about one a quarter), each planned on the projection that includes the earlier orders, a follow-up funded only if the earlier order is funded (DEC-21). The `max_orders=1` path keeps the old hand cases. | One order could not cover the autumn peak; 84347 needed a Q4 2012 order | No |
| 10 Nov | Baseline budget £350 000, Tight £175 000; label "Purchase budget (£, whole horizon)" | A prototype at £100 k left nearly every follow-up unfunded. At £350 k: £349 968 funded, 24 unfunded, £29 145 lost. | No (it replaces £100 k) |
| 10 Nov | 84347 still short in Nov 2012 (2 948 units, about £7 517) is fine as long as it is shown honestly as "Short after plan" with its £ | Its next follow-up doesn't fit the budget; hiding the gap would be dishonest | No |
| 10 Nov | Forecast band = forecast × (1 ± WAPE), floored at 0, labelled "range from last year's forecast error" | A real, documented basis for the range, not a made-up confidence interval | No |
| 10 Nov | Graphite theme (near-black neutrals, blue for plan, amber for budget, red for lead time), replacing the dark navy theme (Change 5, DEC-17) | The owner found the navy theme too much like a chat app. A design review compared 4 token variants and rated Graphite highest (7.5/10). | No |
| 10 Nov | System font stack instead of Inter | Inter at semibold/bold renders U+202F with zero width, so "£349 968" read as "£349968" | No |
| 10 Nov | Overview reading strip (The question / Right now / Do this) and "In plain words:" first in each KPI's help (DEC-23) | The app was hard to follow for someone who doesn't work in purchasing | No |

## 3. Review rounds

Every round followed the same order: a SPEC PR with new or changed ACs and failing tests, then PART PRs, each with a code review and a qa pass, then gate 5. Gate 5 means a smoke run on main plus fresh screenshots and README numbers.

| Round | Found | Changed (PRs) | Dropped or deferred, and why |
| --- | --- | --- | --- |
| Build (09 Nov) | **PART-A:**<br>• qa found float half-up rounding ties and negative zero, fixed with Fraction math.<br>• The reviewer found raw crashes on bad CSVs (blank month, missing columns, integer overflow, negative units), an infinite cover text, validation failing on text input, and capacity counted twice.<br><br>**PART-B:**<br>• The reviewer found a gap in the unfunded flag, a code-first label, a misleading "with plan" line, the Forecast pick lost on page switch, and an unbounded cache.<br>• Visual passes caught truncated KPI cards, word breaks, cut tables and rotated axes. | SPEC #3, #4; PART-A #5; PART-B #6 | — |
| Change 1 and 2 (09 Nov) | "At risk" saturated at 34 of 36; overstock text with no demand; the Custom preset was missing; the UI and core disagreed on "order now" | #4 (AC-35 to AC-37), #7, #8, #9 | — |
| CEO and art director review, round 1 (10 Nov) | 13 fixes:<br>• lost sales in £ and £ tied up<br>• a backtest of the forecast<br>• a flag for later shortfalls<br>• an honest hero card<br>• KPIs after the plan<br>• grouped flags<br>• tables that fit 1280 px<br>• one colour language<br>• a zoomed forecast chart<br>• header and table polish | README counts #10; SPEC #11, #12, #15; PART-A #13; PART-B #14; screenshots #16 | **Dropped:**<br>• Monthly cash budget view: only if a client asks.<br>• Planning several orders: a flag only that round (built in round 3).<br>• Thousands separators inside the sidebar number inputs: a Streamlit limit. |
| CEO and senior designer review, round 2 (10 Nov) | 9 fixes:<br>• full-horizon lost sales as the headline<br>• follow-up orders<br>• a run-out card that shows one decision<br>• a stacked forecast chart with an error band<br>• reorder table by urgency<br>• the same 5 KPIs on every page<br>• a colour lock<br>• the budget label<br>• polish | SPEC #17, #18; PART-A #19; PART-B #20; README and screenshots #21 | **Later:**<br>• A backtest of the plan itself.<br>• Editable Funded ticks.<br>• Product search.<br><br>**Dropped:**<br>• Supplier grouping: no supplier data.<br>• Lost margin: no margin data.<br>• An Expedite button: the app does not act on anything. |
| Owner check and readability polish (10 Nov) | The app was hard to follow for a non-buyer, and the theme felt like a chat app. A preview (not on main) compared 4 theme variants with the reading strip. The design critique added 4 fixes:<br>• the strip moved out of its box<br>• off-white controls<br>• budget-bar label contrast<br>• the Inter separator bug | SPEC #22, #24; PART-B #23; screenshots #25 | The variants that weren't picked were deleted with the preview worktree. |

Review findings that were fixed in later rounds:

| Round | Finding |
| --- | --- |
| Change 3 | The stock-out window was wrong when no order arrives |
| Change 4 | Capacity £ was counted twice in the flags |
| Change 4 | The hero chip was always red |
| Change 4 | The Scenarios text still said £100 000 |
| Change 5 | The Funded colour was skipped because pandas 3 gives string columns the `str` dtype, not `object` |
| Change 5 | The strip copy had edge cases: 0 at risk, singular forms, no run-out card |

## 4. Known limits, leftovers and the later list

| Item | Kind | Why it is like this |
| --- | --- | --- |
| Stock, lead times, MOQ, cost, capacity and inbound orders are synthetic | Limit | No public dataset has real inventory data alongside real demand. Every page labels it. |
| The planning date is fixed at 1 Dec 2011 and the horizon is 6–12 months | Limit | The demand data ends in Nov 2011 |
| Forecast error is 61 % WAPE | Limit | A seasonal naive forecast on noisy wholesale data. It is shown honestly and drawn as a band. Statistical models are out of scope. |
| At most 4 orders per product; one warehouse; no price breaks | Limit | DEC-21 and the spec's out-of-scope list |
| 84347 is still short from Nov 2012 under Baseline | Limit (accepted) | Its next follow-up doesn't fit the budget. It shows as "Short after plan" with its £. |
| No upload of your own data; scenarios are not saved | Limit | Out of scope for a demo |
| Streamlit Community Cloud deploy | Later (owner) | Needs the owner's login. `requirements.txt` is ready. Add the URL to section 1 afterwards. |
| Backtest of the plan itself (Dec 2010 → Nov 2011: £ lost and £ tied up against actuals) | Later | Deferred in round 2. It is a whole new calculation, and the forecast backtest already gives the proof. |
| Editable Funded ticks that recalculate totals | Later | Deferred in round 2. It changes the funding contract (DEC-21). |
| Product search or filter | Later | Deferred in round 2. With 36 products a sorted table is enough. |
| Monthly cash budget view | Later | Only if someone asks for it |
| Thousands separators in the sidebar number inputs | Won't fix | Streamlit `number_input` limit |
| README test counts | Fixed | Updated to 52 acceptance and 379 app checks in PR #26. Update them again whenever tests are added. |
| The spec's "In scope" still says "dark navy theme", and its out-of-scope list repeats "multi-echelon / multi-warehouse" | Leftover | Wording only. DEC-17 is what counts. Fix it in the next SPEC PR. |
| Dependabot PR #2 is open | Leftover | Left alone on purpose. Dependency changes are the owner's call. |

## 5. Gotchas for the next person

| Gotcha | What to do |
| --- | --- |
| **spec-guard needs `Status: approved`.** A spec PR merged while still `draft` turns every later PR red. | Approve in the SPEC PR itself, or open a one-line SPEC PR that sets `Status: approved (Change N)`, as #18 and #24 did. |
| **spec-guard enforces file ownership per part.** One PR that touches both parts' files fails. | Split it into stacked PRs, one per part. |
| **A core change can break PART-B tests.** Examples: the new "at risk" meaning in #13, the follow-ups in #19. | The PART-A PR then has to edit PART-B test files, or it goes red only on those tests and the PART-B PR fixes them. The owner has accepted a red spec-guard with a PR comment that explains it. Say so before asking for a merge. |
| **Squash merges with stacked PRs.** Force-push is blocked. | After the base PR merges, retarget the stacked PR to `main` through the REST API, merge `main` into the branch (no rebase) and wait for green. |
| **`requirements.txt` is owner-protected.** | PRs that touch it go red on spec-guard by design. Regenerate it with `make requirements` and say so in the PR. |
| **Stale server, stale screenshots.** A server started from an old branch serves old code. | Stop it, start `make run` from current main, then take screenshots. Open and look at every PNG before committing. |
| **Playwright Chromium build.** `tools/screenshots.py` needs the Chromium build that matches the locked Playwright (1.64.1). If another install on the machine replaces the browser cache, launching fails. | Run `uv run playwright install chromium`. If that is not possible, a scratch copy of the script with `executable_path` pointing at a cached Chromium gives the same images. Don't change the dependency. |
| **Inter drops U+202F at semibold/bold**, so the thousands separator disappears. | Keep the system font stack (DEC-17). Check the separators in the screenshots. |
| **pandas 3 gives string columns the `str` dtype, not `object`.** | Don't detect text columns by `object` dtype. Use column names. |
| **AppTest blind spots:** it doesn't render `st.html`, and `download_button` has no file name in its proto. | Use `st.markdown` for anything a test must see, and the button label (`Download <file>`) instead of the file name. Use `metric.proto.help` and `proto.delta` for KPI help and sub-lines. |
| **Playwright `inner_text` can't read `st.dataframe`**, because it draws on a canvas. | Check table contents through the core or AppTest, not the browser. |
| **Streamlit drops the widget state of pages that aren't rendered.** | `app.py` writes the Forecast `product` key back to itself on every run so the pick survives. Do the same for any new widget whose value must persist across pages. |
| **ruff's isort sorts first-party imports differently once submodules exist.** Imports in the acceptance tests moved once. | Run `make fix`, then check that only import order changed. |
| **The security scan rejects `random.Random` (S311)**, which the qa tests had used. | Use `numpy.random.default_rng(seed)`. Never add `noqa`. |
| **Pipes hide exit codes.** `make check \| tail` once let a red commit through. | Run `make check` on its own, or check `PIPESTATUS`. |
| **Switching branches while tests run** gives phantom failures. | Use a separate `git worktree` for each parallel lane. |
| **The kit's hooks block** `gh pr`, GraphQL, chained `gh` commands, shell variables in `gh api` paths, force-push and `rm -rf`. A blocked command cancels its whole `&&` chain, commits included. | Use one `gh api` REST call per command and write the paths out literally. |
| **Real-data numbers move when the core changes.** | After every core change, re-run the smoke run and update the README numbers and screenshots in the same gate 5 PR. |

## 6. How to resume

**Process.** Every change follows these steps:
1. **SPEC PR.** Edit `specs/inventory-runout-planner.md`: add or amend ACs and DECs, and set `Status: approved (Change N)`. Add one failing acceptance test per new AC in `tests/acceptance/inventory-runout-planner/`. Title the PR `[inventory-runout-planner/SPEC] …`. Only spec PRs may touch `specs/` and `tests/acceptance/`. Wait for the owner's approval and merge.
2. **PART-A PR** (core), titled `[inventory-runout-planner/PART-A] …`. It touches only PART-A files. Run a code review and a qa pass (qa adds tests under `part-a/`). Done means `make check` passes and the part's acceptance tests pass.
3. **PART-B PR** (UI), the same way with `part-b/`. Stack it on PART-A if it needs the core change.
4. **Gate 5** on main:
   - rebuild the data (`git status` stays clean)
   - smoke run (see the spec's Smoke run section): every page, every preset, Reset, a Custom edit, a bad budget, 4 CSV downloads
   - restart the server from main and retake the screenshots
   - view every PNG
   - update the README numbers
   - open a small PART-B PR with the screenshots and README
5. The owner merges every PR. Never merge your own PR or mark it ready for review.

Use `[no-spec]` docs PRs for text-only fixes such as README counts or this file.

**Where things live.**

| Path | What |
| --- | --- |
| `specs/inventory-runout-planner.md` | ACs, locked decisions (DEC-xx), work split and file ownership, test map, smoke run |
| `src/inventory_runout_planner/` | Core, no Streamlit imports: `models.py`, `data.py`, `synthetic.py`, `planner.py` (`run`, `backtest`, `MAX_ORDERS`), `presets.py`, `exports.py`, `fmt.py` |
| `src/inventory_runout_planner/ui/` | `theme.py` (Graphite tokens, Plotly template, `styled()`), `state.py` (cached `run_scenario`) |
| `app.py`, `app_pages/` | Sidebar, header, KPI strip, reading strip; the five pages |
| `.streamlit/config.toml`, `assets/style.css` | Streamlit theme and CSS |
| `scripts/build_data.py`, `data/` | Data build; committed derived CSVs (`demand_monthly.csv`, `products_synthetic.csv`, `median_prices.csv`) |
| `tools/screenshots.py`, `docs/screenshots/` | Screenshot tool and its output |
| `tests/acceptance/…`, `tests/inventory-runout-planner/part-a`, `…/part-b` | Test layers (section 1) |
| `CLAUDE.md` | Coding rules, guardrails, security rules. Read it first. |

**Picking up a "later" item.** For example, the plan backtest:
1. Read the matching rows in sections 2 and 4 and the DECs they touch. The plan backtest touches DEC-19 and DEC-21.
2. Write down what it changes in the core and what the user sees. Check that it stays within the guardrails: synthetic data labelled, no runtime API calls, no new dependencies.
3. Open a SPEC PR: a new Change N, new ACs with hand-calculated numbers where possible, amended DECs, and failing tests. Then follow the process above.
4. After gate 5, update this file:
   - move the item out of the later list
   - add a row to the decision log, with the numbers that drove the decision
   - add a review-round row if there was a review
   - update the counts in section 1
