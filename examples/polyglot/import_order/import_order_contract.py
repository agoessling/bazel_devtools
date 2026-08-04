"""Keep third-party and Bazel-owned first-party imports in distinct sections."""

import third_party_api

import first_party_api

VALUES = (third_party_api.VALUE, first_party_api.VALUE)
