# Download Analytics Note

PyPI download activity is a directional signal, not an identity-level user
count. Raw package download numbers can include mirrors, CI systems, bots,
automated dependency resolution, cache refreshes, local rebuilds, and repeated
environment creation.

When reporting analytics, keep these categories separate:

- all-time download activity
- recent download activity
- estimated real-user share, when an estimator is available
- mirror/CI-adjusted estimate, when the adjustment method is documented

Use cautious wording:

- "download activity"
- "estimated real-user share"
- "mirror/CI-adjusted estimate"
- "directional signal"

Do not translate downloads into named-person counts, paid account counts,
company rollout claims, or deployed-system claims. If PyPI analytics images are
used, label them as measurement artifacts. They are not proof that a specific
person, team, or organization is running the package.

Any public metric should include the source, time range, and command or artifact
used to collect it. If those are unavailable, describe the observation as
qualitative.
