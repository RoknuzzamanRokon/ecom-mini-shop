import math
import re
import struct
from dataclasses import dataclass
from typing import Any, Optional, Tuple, Union

from django import forms
from django.core.exceptions import ValidationError
from django.db import models

# One WKT number: optional sign, digits with an optional fraction, optional exponent.
_WKT_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_WKT_POINT = re.compile(rf"POINT\s*\(\s*({_WKT_NUMBER})\s+({_WKT_NUMBER})\s*\)", re.IGNORECASE)


class InvalidPointError(ValidationError, ValueError):
    """
    A point that cannot be read or lies off the globe. A ValidationError, so
    forms and full_clean() report it as a field error (BUG-016), and still a
    ValueError for callers that caught the old error.
    """


@dataclass(frozen=True)
class Point:
    """
    Geographic Point representing a real-world coordinate.
    Application coordinate convention:
      - longitude (X): -180.0 to 180.0
      - latitude  (Y):  -90.0 to  90.0
    """
    longitude: float
    latitude: float

    def __post_init__(self):
        object.__setattr__(self, 'longitude', float(self.longitude))
        object.__setattr__(self, 'latitude', float(self.latitude))

    def __str__(self) -> str:
        # WKT, so a form or the admin shows text it can read back.
        return self.to_wkt()

    def validate_range(self) -> "Point":
        """Raise InvalidPointError unless this is a finite coordinate on the globe."""
        if not (math.isfinite(self.longitude) and math.isfinite(self.latitude)):
            raise InvalidPointError("Coordinates must be finite numbers.")
        if not -180.0 <= self.longitude <= 180.0:
            raise InvalidPointError(f"Longitude must be between -180 and 180 (got {self.longitude}).")
        if not -90.0 <= self.latitude <= 90.0:
            raise InvalidPointError(f"Latitude must be between -90 and 90 (got {self.latitude}).")
        return self

    @property
    def x(self) -> float:
        """Alias for longitude (X-axis in standard cartesian/GIS convention)."""
        return self.longitude

    @property
    def y(self) -> float:
        """Alias for latitude (Y-axis in standard cartesian/GIS convention)."""
        return self.latitude

    @property
    def is_empty_or_zero(self) -> bool:
        """Returns True if the point is at (0, 0) - Null Island default placeholder."""
        return abs(self.longitude) < 1e-9 and abs(self.latitude) < 1e-9

    def to_wkt(self) -> str:
        """Generates OpenGIS WKT string: POINT(longitude latitude)."""
        return f"POINT({self.longitude:.7f} {self.latitude:.7f})"

    def to_dict(self) -> dict:
        """Returns coordinate dictionary formatted for API serialization."""
        return {
            "latitude": round(self.latitude, 7),
            "longitude": round(self.longitude, 7),
        }

    @classmethod
    def from_wkb(cls, data: bytes) -> "Point":
        """
        Parses MySQL internal spatial geometry bytes or standard WKB.
        MySQL internal spatial format:
          Bytes 0-3:   SRID (e.g. 4326 in little-endian <I)
          Byte 4:      Byte order (1 = Little Endian)
          Bytes 5-8:   Geometry type (1 = Point in little-endian <I)
          Bytes 9-16:  X coordinate (Longitude when stored with axis-order=long-lat, double <d)
          Bytes 17-24: Y coordinate (Latitude when stored with axis-order=long-lat, double <d)
        """
        if not data:
            return cls(0.0, 0.0)

        # MySQL 4-byte SRID + 21-byte WKB (total 25 bytes)
        if len(data) == 25:
            _srid, _endian, _gtype, lng, lat = struct.unpack('<IBIdd', data)
            return cls(longitude=round(lng, 7), latitude=round(lat, 7))

        # Standard 21-byte WKB without SRID prefix
        if len(data) == 21:
            _endian, _gtype, lng, lat = struct.unpack('<BIdd', data)
            return cls(longitude=round(lng, 7), latitude=round(lat, 7))

        raise ValueError(f"Unrecognized WKB geometry byte length: {len(data)}")

    @classmethod
    def from_wkt(cls, text: str) -> "Point":
        """Parses OpenGIS WKT string: POINT(lng lat). Anything else is InvalidPointError."""
        if not text:
            return cls(0.0, 0.0)
        match = _WKT_POINT.fullmatch(text.strip())
        if not match:
            raise InvalidPointError(
                f"Enter the location as POINT(longitude latitude), for example POINT(90.4125 23.8103); got {text!r}."
            )
        return cls(longitude=float(match.group(1)), latitude=float(match.group(2)))


class PointFormField(forms.CharField):
    """
    Edits a Point as WKT text, POINT(longitude latitude), e.g. in the Django
    admin. It renders the stored point as WKT and reads it back, so opening
    and re-saving a shop round-trips (BUG-016).
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", "POINT(longitude latitude), for example POINT(90.4125 23.8103).")
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        return value.to_wkt() if isinstance(value, Point) else value

    def to_python(self, value):
        text = super().to_python(value)
        if text in self.empty_values:
            return None
        return Point.from_wkt(text).validate_range()


class MySQLPointField(models.Field):
    """
    Custom Django model field mapped to MySQL 8 native `POINT NOT NULL SRID 4326`.
    Uses ST_GeomFromText(%s, 4326, 'axis-order=long-lat') for safe, unambiguous
    longitude/latitude storage and binary WKB unpacking on retrieval.
    Zero GeoDjango/GDAL required.
    """
    description = "MySQL Spatial Point (SRID 4326)"

    def __init__(self, *args, srid: int = 4326, **kwargs):
        self.srid = srid
        kwargs.setdefault('default', 'POINT(0 0)')
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.srid != 4326:
            kwargs['srid'] = self.srid
        return name, path, args, kwargs

    def formfield(self, **kwargs):
        return super().formfield(**{"form_class": PointFormField, **kwargs})

    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        if isinstance(value, Point):
            value.validate_range()

    def value_to_string(self, obj) -> str:
        value = self.value_from_object(obj)
        return value.to_wkt() if isinstance(value, Point) else str(value)

    def db_type(self, connection) -> str:
        if connection.vendor == 'mysql':
            return f"POINT NOT NULL SRID {self.srid}"
        return "POINT"

    def get_placeholder(self, value, compiler, connection) -> str:
        if connection.vendor == 'mysql':
            return f"ST_GeomFromText(%s, {self.srid}, 'axis-order=long-lat')"
        return "%s"

    def get_prep_value(self, value: Any) -> Optional[str]:
        if value is None:
            return "POINT(0 0)"
        if isinstance(value, Point):
            return value.to_wkt()
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return f"POINT({float(value[0]):.7f} {float(value[1]):.7f})"
        if isinstance(value, dict) and 'longitude' in value and 'latitude' in value:
            return f"POINT({float(value['longitude']):.7f} {float(value['latitude']):.7f})"
        if isinstance(value, str):
            value_clean = value.strip()
            if value_clean.upper().startswith("POINT"):
                return value_clean
            raise ValidationError(f"String point must be in WKT format 'POINT(lng lat)', got: {value}")
        raise ValidationError(f"Invalid value type for MySQLPointField: {type(value)}")

    def from_db_value(self, value: Any, expression, connection) -> Point:
        if value is None:
            return Point(0.0, 0.0)
        if isinstance(value, Point):
            return value
        if isinstance(value, bytes):
            return Point.from_wkb(value)
        if isinstance(value, str):
            return Point.from_wkt(value)
        return Point(0.0, 0.0)

    def to_python(self, value: Any) -> Optional[Point]:
        if value is None:
            return Point(0.0, 0.0)
        if isinstance(value, Point):
            return value
        if isinstance(value, bytes):
            return Point.from_wkb(value)
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return Point(longitude=float(value[0]), latitude=float(value[1]))
        if isinstance(value, dict) and 'longitude' in value and 'latitude' in value:
            return Point(longitude=float(value['longitude']), latitude=float(value['latitude']))
        if isinstance(value, str):
            value_clean = value.strip()
            if not value_clean:
                return Point(0.0, 0.0)
            if value_clean.upper().startswith("POINT"):
                return Point.from_wkt(value_clean)
        raise ValidationError(f"Invalid point value: {value}")
