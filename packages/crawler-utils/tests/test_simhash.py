"""SimHash: stability, locality sensitivity, banding, signed conversion."""

from newscrawl_crawler_utils.simhash import (
    BAND_BITS,
    BANDS,
    hamming_distance,
    simhash64,
    simhash_bands,
    to_signed64,
    to_unsigned64,
)

ENGLISH = (
    "The government announced a new economic policy on Thursday that aims to "
    "reduce inflation and stabilize the currency over the next two years. "
    "Officials said the measures include tighter fiscal controls and new "
    "incentives for foreign investment across several key sectors."
)

BANGLA = (
    "সরকার বৃহস্পতিবার একটি নতুন অর্থনৈতিক নীতি ঘোষণা করেছে যার লক্ষ্য "
    "মূল্যস্ফীতি কমানো এবং আগামী দুই বছরে মুদ্রার স্থিতিশীলতা আনা। "
    "কর্মকর্তারা বলেছেন ব্যবস্থাগুলোর মধ্যে রয়েছে কঠোর আর্থিক নিয়ন্ত্রণ এবং "
    "বিভিন্ন খাতে বিদেশি বিনিয়োগের জন্য নতুন প্রণোদনা।"
)


class TestSimhash:
    def test_deterministic(self) -> None:
        assert simhash64(ENGLISH) == simhash64(ENGLISH)
        assert simhash64(BANGLA) == simhash64(BANGLA)

    def test_empty_text_is_zero(self) -> None:
        assert simhash64(None) == 0
        assert simhash64("") == 0
        assert simhash64("   ") == 0

    def test_whitespace_variants_hash_identically(self) -> None:
        messy = ENGLISH.replace(" ", "  \n ")
        assert simhash64(messy) == simhash64(ENGLISH)

    def test_small_edit_gives_small_distance(self) -> None:
        edited = ENGLISH.replace("Thursday", "Friday")
        distance = hamming_distance(simhash64(ENGLISH), simhash64(edited))
        assert 0 < distance <= 10

    def test_different_documents_are_far_apart(self) -> None:
        other = (
            "Rain delayed the third day of the cricket test match in Chattogram, "
            "with only twelve overs bowled before lunch as the home side struggled "
            "to build a lead against a disciplined visiting bowling attack."
        )
        distance = hamming_distance(simhash64(ENGLISH), simhash64(other))
        assert distance > 15

    def test_bangla_small_edit_gives_small_distance(self) -> None:
        edited = BANGLA.replace("বৃহস্পতিবার", "শুক্রবার")
        distance = hamming_distance(simhash64(BANGLA), simhash64(edited))
        assert 0 < distance <= 10


class TestBanding:
    def test_band_count_and_width(self) -> None:
        bands = simhash_bands(simhash64(ENGLISH))
        assert len(bands) == BANDS
        assert all(0 <= band < (1 << BAND_BITS) for band in bands)

    def test_bands_reassemble_to_hash(self) -> None:
        value = simhash64(ENGLISH)
        bands = simhash_bands(value)
        reassembled = sum(band << (i * BAND_BITS) for i, band in enumerate(bands))
        assert reassembled == value

    def test_hashes_within_threshold_share_a_band(self) -> None:
        """Pigeonhole guarantee: <= BANDS-1 flipped bits leave a band intact."""
        value = simhash64(ENGLISH)
        flipped = value ^ 0b111  # 3 bit flips, all in band 0
        assert any(
            a == b for a, b in zip(simhash_bands(value), simhash_bands(flipped), strict=True)
        )
        # Flips spread across 3 different bands still leave one band intact
        spread = value ^ (1 << 0) ^ (1 << 17) ^ (1 << 34)
        assert any(a == b for a, b in zip(simhash_bands(value), simhash_bands(spread), strict=True))


class TestSignedConversion:
    def test_roundtrip(self) -> None:
        for value in (0, 1, 2**63 - 1, 2**63, 2**64 - 1, simhash64(ENGLISH)):
            assert to_unsigned64(to_signed64(value)) == value

    def test_high_bit_becomes_negative(self) -> None:
        assert to_signed64(2**63) == -(2**63)
        assert to_signed64(2**64 - 1) == -1

    def test_signed_band_extraction_matches_unsigned(self) -> None:
        """Postgres extracts bands from the signed value with arithmetic
        shift + mask; results must equal the unsigned extraction."""
        value = simhash64(BANGLA) | (1 << 63)  # force the sign bit
        signed = to_signed64(value)
        for band_index in range(BANDS):
            sql_style = (signed >> (band_index * BAND_BITS)) & 65535
            assert sql_style == simhash_bands(value)[band_index]
