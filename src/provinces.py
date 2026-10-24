"""Thailand's 77 provinces - reference catalogue.

Roster used by validation (definition of done: 77 rows) and by the
dashboard for map centring. Centroids are approximate province-hall points
in EPSG:4326 (WGS 84) at ~1 km precision - sufficient for centring and for
choosing UTM zone 47N vs 48N, but NOT suitable for area or buffer analysis.

Region codes follow NESDC planning regions:
    N = North, NE = Northeast (Isan), C = Central, E = East, W = West, S = South.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.thai_names import THAI_BY_CODE


@dataclass(frozen=True)
class Province:
    """Static reference record for one province.

    Attributes:
        code: Two-digit provincial code as used by DOPA / NESDC.
        name_en: English name.
        name_th: Thai name (from src.thai_names).
        region: NESDC planning region code.
        lat: Latitude in WGS 84 degrees.
        lon: Longitude in WGS 84 degrees.
    """

    code: str
    name_en: str
    name_th: str
    region: str
    lat: float
    lon: float

    @property
    def utm_zone(self) -> str:
        """Preferred UTM zone 47N or 48N for this province."""
        return "EPSG:32647" if self.lon < 102.0 else "EPSG:32648"


# (code, name_en, region, lat, lon)
_RAW: tuple[tuple[str, str, str, float, float], ...] = (
('10', 'Bangkok', 'C', 13.7563, 100.5018),
    ('11', 'Samut Prakan', 'C', 13.5991, 100.5998),
    ('12', 'Nonthaburi', 'C', 13.8591, 100.5217),
    ('13', 'Pathum Thani', 'C', 14.0208, 100.525),
    ('14', 'Phra Nakhon Si Ayutthaya', 'C', 14.3692, 100.5877),
    ('15', 'Ang Thong', 'C', 14.5896, 100.455),
    ('16', 'Lopburi', 'C', 14.7995, 100.6534),
    ('17', 'Sing Buri', 'C', 14.8936, 100.3967),
    ('18', 'Chai Nat', 'C', 15.1851, 100.1251),
    ('19', 'Saraburi', 'C', 14.5289, 100.9101),
    ('20', 'Chonburi', 'E', 13.3611, 100.9847),
    ('21', 'Rayong', 'E', 12.6814, 101.2816),
    ('22', 'Chanthaburi', 'E', 12.6113, 102.1035),
    ('23', 'Trat', 'E', 12.2428, 102.5175),
    ('24', 'Chachoengsao', 'E', 13.6904, 101.0779),
    ('25', 'Prachinburi', 'E', 14.0509, 101.372),
    ('26', 'Nakhon Nayok', 'C', 14.2069, 101.2129),
    ('27', 'Sa Kaeo', 'E', 13.824, 102.0645),
    ('30', 'Nakhon Ratchasima', 'NE', 14.9799, 102.0977),
    ('31', 'Buriram', 'NE', 14.993, 103.1029),
    ('32', 'Surin', 'NE', 14.8829, 103.4937),
    ('33', 'Sisaket', 'NE', 15.1186, 104.322),
    ('34', 'Ubon Ratchathani', 'NE', 15.2448, 104.8473),
    ('35', 'Yasothon', 'NE', 15.7926, 104.1451),
    ('36', 'Chaiyaphum', 'NE', 15.8068, 102.0315),
    ('37', 'Amnat Charoen', 'NE', 15.8657, 104.6258),
    ('38', 'Bueng Kan', 'NE', 18.3609, 103.6466),
    ('39', 'Nong Bua Lamphu', 'NE', 17.2218, 102.426),
    ('40', 'Khon Kaen', 'NE', 16.4419, 102.836),
    ('41', 'Udon Thani', 'NE', 17.4138, 102.7872),
    ('42', 'Loei', 'NE', 17.486, 101.7223),
    ('43', 'Nong Khai', 'NE', 17.8783, 102.742),
    ('44', 'Maha Sarakham', 'NE', 16.185, 103.3007),
    ('45', 'Roi Et', 'NE', 16.0538, 103.652),
    ('46', 'Kalasin', 'NE', 16.4314, 103.5056),
    ('47', 'Sakon Nakhon', 'NE', 17.1545, 104.1348),
    ('48', 'Nakhon Phanom', 'NE', 17.392, 104.7695),
    ('49', 'Mukdahan', 'NE', 16.5421, 104.7235),
    ('50', 'Chiang Mai', 'N', 18.7883, 98.9853),
    ('51', 'Lamphun', 'N', 18.5745, 99.0087),
    ('52', 'Lampang', 'N', 18.2888, 99.4908),
    ('53', 'Uttaradit', 'N', 17.62, 100.0993),
    ('54', 'Phrae', 'N', 18.1445, 100.1403),
    ('55', 'Nan', 'N', 18.7756, 100.773),
    ('56', 'Phayao', 'N', 19.1664, 99.9019),
    ('57', 'Chiang Rai', 'N', 19.9105, 99.8406),
    ('58', 'Mae Hong Son', 'N', 19.302, 97.9654),
    ('60', 'Nakhon Sawan', 'N', 15.7047, 100.1372),
    ('61', 'Uthai Thani', 'N', 15.3835, 100.0245),
    ('62', 'Kamphaeng Phet', 'N', 16.4827, 99.5226),
    ('63', 'Tak', 'W', 16.884, 99.1258),
    ('64', 'Sukhothai', 'N', 17.007, 99.8264),
    ('65', 'Phitsanulok', 'N', 16.8211, 100.2658),
    ('66', 'Phichit', 'N', 16.4418, 100.3488),
    ('67', 'Phetchabun', 'N', 16.419, 101.1606),
    ('70', 'Ratchaburi', 'W', 13.5282, 99.8134),
    ('71', 'Kanchanaburi', 'W', 14.0227, 99.5328),
    ('72', 'Suphan Buri', 'C', 14.4744, 100.1177),
    ('73', 'Nakhon Pathom', 'C', 13.8199, 100.062),
    ('74', 'Samut Sakhon', 'C', 13.5475, 100.2744),
    ('75', 'Samut Songkhram', 'C', 13.4098, 100.0022),
    ('76', 'Phetchaburi', 'W', 13.1119, 99.9395),
    ('77', 'Prachuap Khiri Khan', 'W', 11.8126, 99.7957),
    ('80', 'Nakhon Si Thammarat', 'S', 8.4304, 99.9631),
    ('81', 'Krabi', 'S', 8.0863, 98.9063),
    ('82', 'Phangnga', 'S', 8.4509, 98.5255),
    ('83', 'Phuket', 'S', 7.8804, 98.3923),
    ('84', 'Surat Thani', 'S', 9.1382, 99.3215),
    ('85', 'Ranong', 'S', 9.9529, 98.6085),
    ('86', 'Chumphon', 'S', 10.493, 99.18),
    ('90', 'Songkhla', 'S', 7.1898, 100.5954),
    ('91', 'Satun', 'S', 6.6238, 100.0674),
    ('92', 'Trang', 'S', 7.5594, 99.6114),
    ('93', 'Phatthalung', 'S', 7.6167, 100.0742),
    ('94', 'Pattani', 'S', 6.8695, 101.2501),
    ('95', 'Yala', 'S', 6.541, 101.2804),
    ('96', 'Narathiwat', 'S', 6.4255, 101.8253),
)

PROVINCES: tuple[Province, ...] = tuple(
    Province(c, n, THAI_BY_CODE.get(c, n), r, la, lo)
    for c, n, r, la, lo in _RAW
)

PROVINCE_BY_CODE: dict[str, Province] = {p.code: p for p in PROVINCES}
PROVINCE_BY_NAME: dict[str, Province] = {p.name_en: p for p in PROVINCES}

EXPECTED_PROVINCE_COUNT: int = 77


def assert_catalogue_complete() -> None:
    """Fail fast if the reference catalogue is not exactly 77 provinces.

    Raises:
        AssertionError: When the count or code uniqueness is wrong.
    """
    assert len(PROVINCES) == EXPECTED_PROVINCE_COUNT, (
        f"Province catalogue has {len(PROVINCES)} entries, "
        f"expected {EXPECTED_PROVINCE_COUNT}."
    )
    assert len(PROVINCE_BY_CODE) == len(PROVINCES), "Duplicate codes."
    assert len(PROVINCE_BY_NAME) == len(PROVINCES), "Duplicate names."
