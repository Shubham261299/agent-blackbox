import os

# Privacy rule for this project: nothing leaves the machine. DeepEval ships anonymous product analytics
# (PostHog) unless opted out, and reads this setting when it is first imported -- so set it here, before
# any module of ours can import deepeval. Deliberately a hard assignment, not setdefault.
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
