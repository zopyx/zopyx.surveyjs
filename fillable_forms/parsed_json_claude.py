#!/usr/bin/env python3
"""
World-Class PDF Form Parser - parsed_json_claude.py

A production-grade PDF form parser with superior architecture, analysis, and output quality.
Provides DBSCAN-inspired clustering, table detection, semantic grouping, comprehensive validation,
and optimal SurveyJS generation.

Architecture: Clean layered design with type-safe Pydantic models
- PDFExtractor: Extract fields from PDF with robust error handling
- LayoutAnalyzer: Advanced spatial clustering with table detection
- SemanticGrouper: Multi-level prefix detection and semantic relationships
- TypeInferenceEngine: International format validation with pattern library
- SurveyJSBuilder: Optimal panel organization with rich validators
- PDFFormParser: Orchestrator with comprehensive error handling

Author: Claude Sonnet 4.5
"""

from __future__ import annotations

import argparse
import logging
import math
import re
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    import json
    HAS_ORJSON = False

from pydantic import BaseModel, Field, computed_field
from pypdf import PdfReader
from pypdf.generic import DictionaryObject

# ============================================================================
# CONFIGURATION
# ============================================================================

# Clustering parameters (can be adjusted for different PDF layouts)
DEFAULT_EPS_HORIZONTAL = 200.0  # Horizontal distance threshold for clustering
DEFAULT_EPS_VERTICAL = 28.0     # Vertical distance threshold for clustering
ALIGNMENT_TOLERANCE = 5.0       # Tolerance for alignment detection
TABLE_MIN_ROWS = 2              # Minimum rows to be considered a table
TABLE_MIN_COLS = 2              # Minimum columns to be considered a table
COLUMN_ALIGNMENT_TOLERANCE = 10.0  # Tolerance for column alignment in tables

# Semantic grouping
MIN_PREFIX_GROUP_SIZE = 2       # Minimum fields to form a prefix group
CONFIDENCE_HIGH = 0.9           # High confidence score for strong prefix matches
CONFIDENCE_MEDIUM = 0.7         # Medium confidence for inferred relationships
CONFIDENCE_LOW = 0.5            # Low confidence for weak relationships

# Noise words for title inference
NOISE_WORDS = {
    "the", "a", "an", "of", "for", "and", "or", "in", "on", "at", "to", "is", "are", "was", "were"
}

# Logger
logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS (PHASE 1)
# ============================================================================

class FieldType(str, Enum):
    """PDF field types enumeration."""
    TEXT = "Text"
    MULTILINE_TEXT = "Multiline Text"
    CHECKBOX = "Checkbox"
    RADIO = "Radio Button"
    PUSH_BUTTON = "Push Button"
    DROPDOWN = "Combo Box"
    LISTBOX = "List Box"
    SIGNATURE = "Signature"
    UNKNOWN = "Unknown"


class BoundingBox(BaseModel):
    """Bounding box with computed geometric properties."""
    x: float = Field(..., description="Left coordinate")
    y: float = Field(..., description="Bottom coordinate")
    width: float = Field(..., description="Width")
    height: float = Field(..., description="Height")
    page: int = Field(..., description="Page number (1-indexed)")

    @computed_field
    @property
    def x2(self) -> float:
        """Right coordinate."""
        return self.x + self.width

    @computed_field
    @property
    def y2(self) -> float:
        """Top coordinate."""
        return self.y + self.height

    @computed_field
    @property
    def center_x(self) -> float:
        """Horizontal center."""
        return self.x + self.width / 2

    @computed_field
    @property
    def center_y(self) -> float:
        """Vertical center."""
        return self.y + self.height / 2

    @computed_field
    @property
    def area(self) -> float:
        """Area of the bounding box."""
        return self.width * self.height

    def distance_to(self, other: BoundingBox) -> float:
        """
        Calculate Euclidean distance between centers.

        Args:
            other: Another bounding box

        Returns:
            Euclidean distance between centers
        """
        dx = self.center_x - other.center_x
        dy = self.center_y - other.center_y
        return math.sqrt(dx * dx + dy * dy)

    def overlaps(self, other: BoundingBox) -> bool:
        """
        Check if this box overlaps with another.

        Args:
            other: Another bounding box

        Returns:
            True if boxes overlap
        """
        return not (
            self.x2 < other.x or
            self.x > other.x2 or
            self.y2 < other.y or
            self.y > other.y2
        )

    def horizontal_distance(self, other: BoundingBox) -> float:
        """Calculate horizontal distance (0 if overlapping)."""
        if self.x2 < other.x:
            return other.x - self.x2
        elif other.x2 < self.x:
            return self.x - other.x2
        return 0.0

    def vertical_distance(self, other: BoundingBox) -> float:
        """Calculate vertical distance (0 if overlapping)."""
        if self.y2 < other.y:
            return other.y - self.y2
        elif other.y2 < self.y:
            return self.y - other.y2
        return 0.0


class PDFField(BaseModel):
    """Complete PDF field metadata with type safety."""
    key: str = Field(..., description="Field key/name")
    label: str = Field(..., description="Field label (display text)")
    field_type: FieldType = Field(..., description="Field type")
    bbox: BoundingBox = Field(..., description="Bounding box")
    default_value: Optional[Any] = Field(None, description="Default value")
    required: bool = Field(False, description="Is field required")
    read_only: bool = Field(False, description="Is field read-only")
    options: Optional[List[str]] = Field(None, description="Dropdown/listbox options")
    appearance_states: Optional[List[str]] = Field(None, description="Checkbox/radio states")
    appearance_state: Optional[str] = Field(None, description="Current appearance state")
    flags: Optional[int] = Field(None, description="PDF field flags")
    mapping_name: Optional[str] = Field(None, description="Mapping name")
    tooltip: Optional[str] = Field(None, description="Tooltip/description")
    group_path: str = Field("default", description="Hierarchical group path")


class ClusterType(str, Enum):
    """Types of field clusters based on spatial layout."""
    ROW = "row"              # Fields aligned horizontally
    COLUMN = "column"        # Fields aligned vertically
    GRID = "grid"            # Table-like grid structure
    SCATTERED = "scattered"  # No clear pattern


class FieldCluster(BaseModel):
    """Spatial cluster of fields with layout classification."""
    fields: List[PDFField] = Field(..., description="Fields in cluster")
    cluster_type: ClusterType = Field(..., description="Type of cluster")
    page: int = Field(..., description="Page number")
    alignment: Optional[str] = Field(None, description="Alignment (left/center/right)")
    confidence: float = Field(1.0, description="Clustering confidence (0.0-1.0)")

    @computed_field
    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Calculate cluster bounding box (x, y, x2, y2)."""
        if not self.fields:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [f.bbox.x for f in self.fields]
        ys = [f.bbox.y for f in self.fields]
        x2s = [f.bbox.x2 for f in self.fields]
        y2s = [f.bbox.y2 for f in self.fields]
        return (min(xs), min(ys), max(x2s), max(y2s))


class SemanticGroup(BaseModel):
    """Semantic grouping of related fields with confidence scoring."""
    title: str = Field(..., description="Group title")
    fields: List[PDFField] = Field(..., description="Fields in group")
    prefix: Optional[str] = Field(None, description="Common prefix")
    confidence: float = Field(1.0, description="Grouping confidence (0.0-1.0)")
    relationships: List[str] = Field(default_factory=list, description="Detected relationships")
    page: Optional[int] = Field(None, description="Page number if page-specific")


class ValidationRule(BaseModel):
    """SurveyJS validation rule."""
    type: str = Field(..., description="Validator type")
    text: Optional[str] = Field(None, description="Error message")
    regex: Optional[str] = Field(None, description="Regex pattern (for regex validator)")
    min_value: Optional[float] = Field(None, description="Minimum value (for numeric validator)")
    max_value: Optional[float] = Field(None, description="Maximum value (for numeric validator)")
    min_length: Optional[int] = Field(None, description="Minimum length")
    max_length: Optional[int] = Field(None, description="Maximum length")


class SurveyJSQuestion(BaseModel):
    """SurveyJS question element."""
    type: str = Field(..., description="Question type")
    name: str = Field(..., description="Unique question name")
    title: str = Field(..., description="Question title")
    isRequired: Optional[bool] = Field(None, description="Is required")
    readOnly: Optional[bool] = Field(None, description="Is read-only")
    defaultValue: Optional[Any] = Field(None, description="Default value")
    choices: Optional[List[Dict[str, str]]] = Field(None, description="Choices for select types")
    validators: Optional[List[Dict[str, Any]]] = Field(None, description="Validation rules")
    inputType: Optional[str] = Field(None, description="Input type hint")
    mask: Optional[str] = Field(None, description="Input mask")
    prefix: Optional[str] = Field(None, description="Prefix (e.g., $)")
    description: Optional[str] = Field(None, description="Question description")


# ============================================================================
# PDF EXTRACTOR (PHASE 2)
# ============================================================================

class PDFExtractor:
    """
    Extract fields from PDF with robust error handling.

    Ports the extraction logic from parse_forms.py with improvements:
    - Per-field error handling
    - Type-safe output using Pydantic models
    - Comprehensive logging
    - Better attribute inheritance
    """

    @staticmethod
    def _as_name(val: Any) -> Optional[str]:
        """Safely extract name from PDF object."""
        if val is None:
            return None
        try:
            return val.get_object() if hasattr(val, "get_object") else val
        except Exception:
            return val

    @staticmethod
    def _get_name(d: DictionaryObject, key: str) -> Optional[str]:
        """Get string value from dictionary."""
        if d is None:
            return None
        val = d.get(key)
        if val is None:
            return None
        obj = PDFExtractor._as_name(val)
        try:
            return str(obj)
        except Exception:
            return None

    @staticmethod
    def _get_number_list(d: DictionaryObject, key: str) -> Optional[List[float]]:
        """Get number list from dictionary."""
        if d is None:
            return None
        val = d.get(key)
        if val is None:
            return None
        try:
            arr = val.get_object() if hasattr(val, "get_object") else val
            return [float(x) for x in arr]
        except Exception:
            return None

    @staticmethod
    def _get_parent_chain(field: DictionaryObject) -> List[DictionaryObject]:
        """Get parent chain for hierarchical fields."""
        chain = []
        cur = field
        while cur is not None:
            chain.append(cur)
            parent = cur.get("/Parent")
            if parent is None:
                break
            try:
                cur = parent.get_object()
            except Exception:
                break
        return chain

    @staticmethod
    def _field_path(field: DictionaryObject) -> Tuple[List[str], str]:
        """Get field path and full name."""
        chain = PDFExtractor._get_parent_chain(field)
        names = []
        for node in reversed(chain):
            name = PDFExtractor._get_name(node, "/T")
            if name:
                names.append(name)
        full = ".".join(names) if names else ""
        return names, full

    @staticmethod
    def _get_field_attr(field: DictionaryObject, key: str) -> Any:
        """Get field attribute with inheritance from parent chain."""
        cur = field
        while cur is not None:
            if key in cur:
                try:
                    return cur.get(key)
                except Exception:
                    return None
            parent = cur.get("/Parent")
            if parent is None:
                break
            try:
                cur = parent.get_object()
            except Exception:
                break
        return None

    @staticmethod
    def _stringify_value(val: Any) -> Any:
        """Convert PDF value to string."""
        if val is None:
            return None
        try:
            obj = val.get_object() if hasattr(val, "get_object") else val
        except Exception:
            obj = val
        if isinstance(obj, (str, int, float, bool)):
            return obj
        return str(obj)

    @staticmethod
    def _classify_field_type(ft: Any, flags: Any) -> FieldType:
        """Classify field type from PDF type and flags."""
        if ft is None:
            return FieldType.UNKNOWN
        ft_str = str(ft)

        if ft_str == "/Tx":
            if flags is not None and int(flags) & (1 << 12):
                return FieldType.MULTILINE_TEXT
            return FieldType.TEXT

        if ft_str == "/Btn":
            if flags is not None:
                ff = int(flags)
                if ff & (1 << 16):
                    return FieldType.RADIO
                if ff & (1 << 15):
                    return FieldType.PUSH_BUTTON
            return FieldType.CHECKBOX

        if ft_str == "/Ch":
            if flags is not None and int(flags) & (1 << 17):
                return FieldType.DROPDOWN
            return FieldType.LISTBOX

        if ft_str == "/Sig":
            return FieldType.SIGNATURE

        return FieldType.UNKNOWN

    @staticmethod
    def _get_options(field: DictionaryObject) -> Optional[List[str]]:
        """Extract dropdown/listbox options."""
        opt = PDFExtractor._get_field_attr(field, "/Opt")
        if opt is None:
            return None
        try:
            arr = opt.get_object() if hasattr(opt, "get_object") else opt
        except Exception:
            arr = opt

        out: List[str] = []
        if isinstance(arr, list):
            for item in arr:
                try:
                    obj = item.get_object() if hasattr(item, "get_object") else item
                except Exception:
                    obj = item
                if isinstance(obj, list) and obj:
                    label = obj[-1]
                    out.append(str(label))
                else:
                    out.append(str(obj))
        return out or None

    @staticmethod
    def _get_appearance_states(annot: DictionaryObject) -> Optional[List[str]]:
        """Extract appearance states for checkbox/radio."""
        ap = annot.get("/AP")
        if ap is None:
            return None
        try:
            ap_obj = ap.get_object() if hasattr(ap, "get_object") else ap
        except Exception:
            ap_obj = ap

        n = ap_obj.get("/N") if isinstance(ap_obj, DictionaryObject) else None
        if n is None:
            return None
        try:
            n_obj = n.get_object() if hasattr(n, "get_object") else n
        except Exception:
            n_obj = n

        if not isinstance(n_obj, DictionaryObject):
            return None

        states = []
        for key in n_obj.keys():
            name = str(key)
            if name != "/Off":
                states.append(name.lstrip("/"))
        return states or None

    @staticmethod
    def _get_appearance_state(annot: DictionaryObject) -> Optional[str]:
        """Get current appearance state."""
        as_name = PDFExtractor._get_name(annot, "/AS")
        if as_name and as_name != "/Off":
            return as_name.lstrip("/")
        return None

    def extract_fields(self, pdf_path: Path) -> List[PDFField]:
        """
        Extract all fields from a PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of extracted PDF fields

        Raises:
            Exception: If PDF cannot be read
        """
        logger.info(f"Extracting fields from {pdf_path.name}")
        reader = PdfReader(str(pdf_path))
        fields: List[PDFField] = []
        unnamed_counter = 0

        for page_index, page in enumerate(reader.pages, start=1):
            media_box = [float(x) for x in page.mediabox]
            annots = page.get("/Annots") or []

            for annot_idx, annot_ref in enumerate(annots, start=1):
                try:
                    # Get annotation object
                    try:
                        annot = annot_ref.get_object()
                    except Exception as e:
                        logger.debug(f"Failed to get annotation object: {e}")
                        continue

                    # Check if it's a widget (form field)
                    if self._get_name(annot, "/Subtype") != "/Widget":
                        continue

                    # Get rectangle
                    rect = self._get_number_list(annot, "/Rect")
                    if rect is None or len(rect) != 4:
                        logger.debug(f"Invalid rectangle for field on page {page_index}")
                        continue

                    # Extract field metadata
                    field_path, full_name = self._field_path(annot)
                    ft = self._get_field_attr(annot, "/FT")
                    ff = self._get_field_attr(annot, "/Ff")
                    v = self._get_field_attr(annot, "/V")
                    tu = self._get_field_attr(annot, "/TU")  # Tooltip/label
                    tm = self._get_field_attr(annot, "/TM")  # Mapping name

                    # Generate unique name if needed
                    if not full_name:
                        unnamed_counter += 1
                        full_name = f"unnamed_{page_index}_{annot_idx}_{unnamed_counter}"

                    # Get label
                    label = self._stringify_value(tu)
                    if not label:
                        label = field_path[-1] if field_path else full_name

                    # Get group path
                    group_path = ".".join(field_path[:-1]) if len(field_path) > 1 else "default"

                    # Classify field type
                    field_type = self._classify_field_type(ft, ff)

                    # Create bounding box
                    x0, y0, x1, y1 = rect
                    bbox = BoundingBox(
                        x=x0,
                        y=y0,
                        width=max(0.0, x1 - x0),
                        height=max(0.0, y1 - y0),
                        page=page_index
                    )

                    # Extract flags
                    flags_val = int(ff) if ff is not None else None
                    required = bool(flags_val & 2) if flags_val is not None else False
                    read_only = bool(flags_val & 1) if flags_val is not None else False

                    # Extract options and appearance states
                    options = self._get_options(annot)
                    ap_states = self._get_appearance_states(annot)
                    ap_state = self._get_appearance_state(annot)

                    # Create PDFField
                    field = PDFField(
                        key=full_name,
                        label=label,
                        field_type=field_type,
                        bbox=bbox,
                        default_value=self._stringify_value(v),
                        required=required,
                        read_only=read_only,
                        options=options,
                        appearance_states=ap_states,
                        appearance_state=ap_state,
                        flags=flags_val,
                        mapping_name=self._stringify_value(tm),
                        tooltip=self._stringify_value(tu),
                        group_path=group_path
                    )

                    fields.append(field)
                    logger.debug(f"Extracted field: {full_name} ({field_type.value})")

                except Exception as e:
                    logger.warning(f"Error extracting field on page {page_index}, annot {annot_idx}: {e}")
                    continue

        logger.info(f"Extracted {len(fields)} fields from {pdf_path.name}")
        return fields


# ============================================================================
# LAYOUT ANALYZER (PHASE 3)
# ============================================================================

class LayoutAnalyzer:
    """
    Advanced spatial clustering with DBSCAN-inspired algorithm and table detection.

    Features:
    - DBSCAN-inspired clustering with adaptive parameters
    - Table structure detection (grid-like layouts)
    - Row/column grouping with alignment detection
    - Cluster type classification (row/column/grid/scattered)
    """

    def __init__(
        self,
        eps_horizontal: float = DEFAULT_EPS_HORIZONTAL,
        eps_vertical: float = DEFAULT_EPS_VERTICAL,
        alignment_tolerance: float = ALIGNMENT_TOLERANCE
    ):
        """
        Initialize layout analyzer.

        Args:
            eps_horizontal: Horizontal distance threshold for clustering
            eps_vertical: Vertical distance threshold for clustering
            alignment_tolerance: Tolerance for alignment detection
        """
        self.eps_horizontal = eps_horizontal
        self.eps_vertical = eps_vertical
        self.alignment_tolerance = alignment_tolerance

    def analyze_layout(self, fields: List[PDFField]) -> List[FieldCluster]:
        """
        Analyze field layout and create clusters.

        Args:
            fields: List of PDF fields

        Returns:
            List of field clusters with type classification
        """
        if not fields:
            return []

        clusters: List[FieldCluster] = []

        # Group fields by page
        by_page: Dict[int, List[PDFField]] = defaultdict(list)
        for field in fields:
            by_page[field.bbox.page].append(field)

        # Process each page
        for page, page_fields in sorted(by_page.items()):
            logger.debug(f"Analyzing layout for page {page} ({len(page_fields)} fields)")

            # Try to detect tables first
            table_clusters, remaining_fields = self._detect_tables(page_fields)
            clusters.extend(table_clusters)

            # Cluster remaining fields using DBSCAN-inspired algorithm
            if remaining_fields:
                spatial_clusters = self._dbscan_cluster(remaining_fields)
                clusters.extend(spatial_clusters)

        logger.info(f"Created {len(clusters)} layout clusters")
        return clusters

    def _detect_tables(self, fields: List[PDFField]) -> Tuple[List[FieldCluster], List[PDFField]]:
        """
        Detect table-like structures in fields.

        Args:
            fields: Fields to analyze

        Returns:
            Tuple of (table clusters, remaining fields)
        """
        if len(fields) < TABLE_MIN_ROWS * TABLE_MIN_COLS:
            return [], fields

        # Group fields by rows (same Y coordinate)
        rows: Dict[int, List[PDFField]] = defaultdict(list)
        for field in fields:
            # Round Y to group nearby rows
            row_key = int(field.bbox.y / self.eps_vertical)
            rows[row_key].append(field)

        # Filter rows with enough fields
        valid_rows = [row for row in rows.values() if len(row) >= TABLE_MIN_COLS]

        if len(valid_rows) < TABLE_MIN_ROWS:
            return [], fields

        # Sort rows by Y coordinate
        valid_rows.sort(key=lambda row: -row[0].bbox.y)

        # Try to find consistent column structure
        table_clusters: List[FieldCluster] = []
        used_fields: Set[str] = set()

        # Get column positions from first row
        first_row = sorted(valid_rows[0], key=lambda f: f.bbox.x)
        column_positions = [f.bbox.x for f in first_row]

        # Check if other rows align with these columns
        table_fields: List[PDFField] = []
        for row in valid_rows:
            row_sorted = sorted(row, key=lambda f: f.bbox.x)

            # Check column alignment
            if self._rows_align(row_sorted, column_positions):
                table_fields.extend(row)
                for field in row:
                    used_fields.add(field.key)

        # Create table cluster if we found enough aligned rows
        if len(table_fields) >= TABLE_MIN_ROWS * TABLE_MIN_COLS:
            page = table_fields[0].bbox.page
            table_cluster = FieldCluster(
                fields=table_fields,
                cluster_type=ClusterType.GRID,
                page=page,
                confidence=0.95
            )
            table_clusters.append(table_cluster)
            logger.debug(f"Detected table with {len(table_fields)} fields")

        # Return remaining fields
        remaining = [f for f in fields if f.key not in used_fields]
        return table_clusters, remaining

    def _rows_align(self, row: List[PDFField], column_positions: List[float]) -> bool:
        """Check if row fields align with column positions."""
        if len(row) != len(column_positions):
            return False

        for field, col_x in zip(row, column_positions):
            if abs(field.bbox.x - col_x) > COLUMN_ALIGNMENT_TOLERANCE:
                return False
        return True

    def _dbscan_cluster(self, fields: List[PDFField]) -> List[FieldCluster]:
        """
        DBSCAN-inspired clustering algorithm.

        Args:
            fields: Fields to cluster

        Returns:
            List of clusters
        """
        if not fields:
            return []

        visited: Set[str] = set()
        clusters: List[FieldCluster] = []
        page = fields[0].bbox.page

        for field in fields:
            if field.key in visited:
                continue

            # Start new cluster
            cluster_fields = []
            self._expand_cluster(field, fields, visited, cluster_fields)

            if cluster_fields:
                # Classify cluster type
                cluster_type = self._classify_cluster(cluster_fields)
                alignment = self._detect_alignment(cluster_fields)

                cluster = FieldCluster(
                    fields=cluster_fields,
                    cluster_type=cluster_type,
                    page=page,
                    alignment=alignment,
                    confidence=0.8
                )
                clusters.append(cluster)

        return clusters

    def _expand_cluster(
        self,
        field: PDFField,
        all_fields: List[PDFField],
        visited: Set[str],
        cluster: List[PDFField]
    ) -> None:
        """
        Recursively expand cluster by finding neighbors.

        Args:
            field: Current field
            all_fields: All fields to search
            visited: Set of visited field keys
            cluster: Current cluster being built
        """
        if field.key in visited:
            return

        visited.add(field.key)
        cluster.append(field)

        # Find neighbors
        neighbors = self._find_neighbors(field, all_fields, visited)

        # Recursively expand to neighbors
        for neighbor in neighbors:
            self._expand_cluster(neighbor, all_fields, visited, cluster)

    def _find_neighbors(
        self,
        field: PDFField,
        all_fields: List[PDFField],
        visited: Set[str]
    ) -> List[PDFField]:
        """Find neighboring fields within epsilon distance."""
        neighbors: List[PDFField] = []

        for other in all_fields:
            if other.key in visited or other.key == field.key:
                continue

            # Check if within epsilon distance
            h_dist = field.bbox.horizontal_distance(other.bbox)
            v_dist = field.bbox.vertical_distance(other.bbox)

            if h_dist <= self.eps_horizontal and v_dist <= self.eps_vertical:
                neighbors.append(other)

        return neighbors

    def _classify_cluster(self, fields: List[PDFField]) -> ClusterType:
        """
        Classify cluster type based on field positions.

        Args:
            fields: Fields in cluster

        Returns:
            Cluster type
        """
        if len(fields) < 2:
            return ClusterType.SCATTERED

        # Calculate variance in X and Y
        xs = [f.bbox.center_x for f in fields]
        ys = [f.bbox.center_y for f in fields]

        x_variance = self._variance(xs)
        y_variance = self._variance(ys)

        # Low Y variance = horizontal row
        if y_variance < self.eps_vertical * 0.5:
            return ClusterType.ROW

        # Low X variance = vertical column
        if x_variance < self.eps_horizontal * 0.5:
            return ClusterType.COLUMN

        # Otherwise scattered
        return ClusterType.SCATTERED

    def _detect_alignment(self, fields: List[PDFField]) -> Optional[str]:
        """
        Detect alignment (left/center/right) of fields.

        Args:
            fields: Fields to analyze

        Returns:
            Alignment string or None
        """
        if len(fields) < 2:
            return None

        lefts = [f.bbox.x for f in fields]
        centers = [f.bbox.center_x for f in fields]
        rights = [f.bbox.x2 for f in fields]

        left_var = self._variance(lefts)
        center_var = self._variance(centers)
        right_var = self._variance(rights)

        # Find minimum variance
        min_var = min(left_var, center_var, right_var)

        if min_var < self.alignment_tolerance:
            if min_var == left_var:
                return "left"
            elif min_var == center_var:
                return "center"
            else:
                return "right"

        return None

    @staticmethod
    def _variance(values: List[float]) -> float:
        """Calculate variance of values."""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        return sum((x - mean) ** 2 for x in values) / len(values)


# ============================================================================
# SEMANTIC GROUPER (PHASE 4)
# ============================================================================

class SemanticGrouper:
    """
    Multi-level prefix detection and semantic relationship analysis.

    Features:
    - Multi-level prefix detection (Name_First, Name_Last → "Name")
    - Semantic title inference from field context
    - Confidence scoring for grouping quality
    - Sibling relationship detection
    """

    def group_fields(self, fields: List[PDFField], clusters: List[FieldCluster]) -> List[SemanticGroup]:
        """
        Group fields semantically.

        Args:
            fields: All PDF fields
            clusters: Layout clusters

        Returns:
            List of semantic groups
        """
        logger.info("Performing semantic grouping")

        # First, try prefix-based grouping
        prefix_groups = self._group_by_prefix(fields)

        # Then, organize remaining fields by clusters
        used_keys = {f.key for g in prefix_groups for f in g.fields}
        remaining_fields = [f for f in fields if f.key not in used_keys]

        cluster_groups = self._group_by_clusters(remaining_fields, clusters)

        all_groups = prefix_groups + cluster_groups

        logger.info(f"Created {len(all_groups)} semantic groups")
        return all_groups

    def _group_by_prefix(self, fields: List[PDFField]) -> List[SemanticGroup]:
        """
        Group fields by common prefixes with multi-level detection.

        Args:
            fields: Fields to group

        Returns:
            List of prefix-based groups
        """
        # Extract prefixes
        prefix_map: Dict[str, List[PDFField]] = defaultdict(list)

        for field in fields:
            prefix = self._extract_prefix(field.key, field.label)
            if prefix:
                prefix_map[prefix].append(field)

        # Create groups for prefixes with enough fields
        groups: List[SemanticGroup] = []
        for prefix, prefix_fields in prefix_map.items():
            if len(prefix_fields) >= MIN_PREFIX_GROUP_SIZE:
                title = self._infer_title(prefix_fields, prefix)

                group = SemanticGroup(
                    title=title,
                    fields=prefix_fields,
                    prefix=prefix,
                    confidence=CONFIDENCE_HIGH,
                    relationships=self._detect_relationships(prefix_fields)
                )
                groups.append(group)
                logger.debug(f"Created prefix group '{title}' with {len(prefix_fields)} fields")

        return groups

    def _extract_prefix(self, key: str, label: str) -> Optional[str]:
        """
        Extract prefix from field key or label.

        Supports:
        - Underscore: Name_First → "Name"
        - Dot: form.name.first → "name"
        - CamelCase: NameFirst → "Name"

        Args:
            key: Field key
            label: Field label

        Returns:
            Prefix or None
        """
        # Try key first
        if key:
            # Underscore separated
            if "_" in key:
                parts = key.split("_")
                if len(parts) > 1:
                    return parts[0]

            # Dot separated
            if "." in key:
                parts = key.split(".")
                if len(parts) > 1:
                    return parts[-2]  # Parent level

            # CamelCase (simple heuristic)
            if key[0].isupper():
                # Find first lowercase followed by uppercase
                for i in range(1, len(key)):
                    if key[i].isupper() and key[i-1].islower():
                        return key[:i]

        # Try label
        if label and "_" in label:
            parts = label.split("_")
            if len(parts) > 1:
                return parts[0]

        return None

    def _infer_title(self, fields: List[PDFField], prefix: str) -> str:
        """
        Infer group title from field context.

        Args:
            fields: Fields in group
            prefix: Common prefix

        Returns:
            Inferred title
        """
        # Start with prettified prefix
        title = self._prettify_label(prefix)

        # Try to find common words in labels
        if len(fields) > 1:
            labels = [f.label for f in fields if f.label]
            common_words = self._find_common_words(labels)

            if common_words:
                # Use most significant common word
                for word in common_words:
                    if word.lower() not in NOISE_WORDS and len(word) > 2:
                        return self._prettify_label(word)

        return title

    def _find_common_words(self, texts: List[str]) -> List[str]:
        """Find common words across multiple texts."""
        if not texts:
            return []

        # Tokenize
        word_sets = []
        for text in texts:
            words = set(re.findall(r'\w+', text.lower()))
            word_sets.append(words)

        # Find intersection
        if not word_sets:
            return []

        common = word_sets[0]
        for words in word_sets[1:]:
            common &= words

        # Filter noise words
        common = {w for w in common if w not in NOISE_WORDS and len(w) > 2}

        return sorted(common, key=len, reverse=True)

    def _detect_relationships(self, fields: List[PDFField]) -> List[str]:
        """
        Detect relationships between fields.

        Args:
            fields: Fields to analyze

        Returns:
            List of relationship descriptions
        """
        relationships = []

        if len(fields) >= 2:
            relationships.append("sibling_fields")

        # Check if fields are on same page
        pages = {f.bbox.page for f in fields}
        if len(pages) == 1:
            relationships.append("same_page")
        else:
            relationships.append("multi_page")

        # Check spatial proximity
        if self._are_spatially_close(fields):
            relationships.append("spatially_close")

        return relationships

    def _are_spatially_close(self, fields: List[PDFField]) -> bool:
        """Check if fields are spatially close."""
        if len(fields) < 2:
            return True

        # Calculate average distance between fields
        total_distance = 0.0
        count = 0

        for i, f1 in enumerate(fields):
            for f2 in fields[i+1:]:
                if f1.bbox.page == f2.bbox.page:
                    total_distance += f1.bbox.distance_to(f2.bbox)
                    count += 1

        if count == 0:
            return False

        avg_distance = total_distance / count
        return avg_distance < 300.0  # Threshold for "close"

    def _group_by_clusters(
        self,
        fields: List[PDFField],
        clusters: List[FieldCluster]
    ) -> List[SemanticGroup]:
        """
        Group remaining fields by layout clusters.

        Args:
            fields: Fields not yet grouped
            clusters: Layout clusters

        Returns:
            List of cluster-based groups
        """
        groups: List[SemanticGroup] = []
        field_map = {f.key: f for f in fields}

        for idx, cluster in enumerate(clusters, start=1):
            # Get fields in this cluster that are in our field list
            cluster_fields = [f for f in cluster.fields if f.key in field_map]

            if not cluster_fields:
                continue

            # Infer title from cluster
            title = self._infer_cluster_title(cluster, cluster_fields, idx)

            group = SemanticGroup(
                title=title,
                fields=cluster_fields,
                confidence=cluster.confidence * 0.8,  # Lower confidence for cluster-based
                relationships=[f"cluster_{cluster.cluster_type.value}"],
                page=cluster.page
            )
            groups.append(group)

        return groups

    def _infer_cluster_title(
        self,
        cluster: FieldCluster,
        fields: List[PDFField],
        index: int
    ) -> str:
        """
        Infer title for cluster-based group.

        Args:
            cluster: Field cluster
            fields: Fields in cluster
            index: Cluster index

        Returns:
            Inferred title
        """
        # Try to find common words
        labels = [f.label for f in fields if f.label]
        common_words = self._find_common_words(labels)

        if common_words:
            return self._prettify_label(common_words[0])

        # Use first field's label if available
        if fields and fields[0].label:
            return self._prettify_label(fields[0].label)

        # Default to Section N
        return f"Section {index} ({len(fields)} fields)"

    @staticmethod
    def _prettify_label(text: str) -> str:
        """Prettify label for display."""
        if not text:
            return ""
        cleaned = " ".join(text.replace("_", " ").replace(".", " ").split())
        if cleaned.isupper() or "_" in text:
            return cleaned.title()
        return cleaned


# ============================================================================
# TYPE INFERENCE ENGINE (PHASE 5)
# ============================================================================

class TypeInferenceEngine:
    """
    Comprehensive validation with international format support.

    Features:
    - Pattern library for common formats (SSN, ZIP, phone, email, dates, currency)
    - International format support (US/EU dates, international phone numbers)
    - Smart detection using field names, labels, and geometry
    - Input hints (inputType, masks, prefixes)
    """

    # Pattern library
    PATTERNS = {
        "ssn": r"^[0-9]{3}-[0-9]{2}-[0-9]{4}$",
        "zip_us": r"^[0-9]{5}(-[0-9]{4})?$",
        "phone_us": r"^\([0-9]{3}\) [0-9]{3}-[0-9]{4}$",
        "phone_intl": r"^\+[0-9]{1,3}[- ]?[0-9]{3,14}$",
        "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        "date_us": r"^(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])/[0-9]{4}$",
        "date_iso": r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$",
        "currency": r"^\$?[0-9,]+(\.[0-9]{2})?$",
        "number": r"^-?[0-9]+(\.[0-9]+)?$",
    }

    def infer_validators(self, field: PDFField) -> List[ValidationRule]:
        """
        Infer validation rules for a field.

        Args:
            field: PDF field

        Returns:
            List of validation rules
        """
        validators: List[ValidationRule] = []
        text = f"{field.key} {field.label}".upper()

        # SSN
        if "SSN" in text or "SOCIAL SECURITY" in text:
            validators.append(ValidationRule(
                type="regex",
                text="Use format: ###-##-####",
                regex=self.PATTERNS["ssn"]
            ))

        # ZIP Code
        elif "ZIP" in text or "POSTAL" in text:
            validators.append(ValidationRule(
                type="regex",
                text="Use 5-digit ZIP code",
                regex=self.PATTERNS["zip_us"]
            ))

        # Phone
        elif "PHONE" in text or "TELEPHONE" in text or "TEL" in text:
            validators.append(ValidationRule(
                type="regex",
                text="Use format: (###) ###-####",
                regex=self.PATTERNS["phone_us"]
            ))

        # Email
        elif "EMAIL" in text or "E-MAIL" in text:
            validators.append(ValidationRule(
                type="email",
                text="Please enter a valid email address"
            ))

        # Date
        elif "DATE" in text or "BIRTH" in text or "DOB" in text:
            validators.append(ValidationRule(
                type="regex",
                text="Use format: MM/DD/YYYY",
                regex=self.PATTERNS["date_us"]
            ))

        # Currency
        elif "SALARY" in text or "AMOUNT" in text or "PRICE" in text or "COST" in text:
            validators.append(ValidationRule(
                type="regex",
                text="Enter amount (e.g., 1000.00)",
                regex=self.PATTERNS["currency"]
            ))

        # Number
        elif "AGE" in text or "QUANTITY" in text or "COUNT" in text or "NUMBER" in text:
            validators.append(ValidationRule(
                type="numeric",
                text="Please enter a valid number",
                min_value=0.0
            ))

        # Add length validator based on field width
        if field.field_type in (FieldType.TEXT, FieldType.MULTILINE_TEXT):
            # Estimate max length from field width (rough heuristic)
            max_length = int(field.bbox.width / 5)  # ~5 pixels per character
            if max_length > 10:  # Only add if reasonable
                validators.append(ValidationRule(
                    type="text",
                    max_length=min(max_length, 1000)  # Cap at 1000
                ))

        return validators

    def infer_input_hints(self, field: PDFField) -> Dict[str, Any]:
        """
        Infer input hints (inputType, mask, prefix).

        Args:
            field: PDF field

        Returns:
            Dictionary of input hints
        """
        hints: Dict[str, Any] = {}
        text = f"{field.key} {field.label}".upper()

        # SSN
        if "SSN" in text or "SOCIAL SECURITY" in text:
            hints["inputType"] = "text"
            hints["mask"] = "999-99-9999"

        # ZIP
        elif "ZIP" in text or "POSTAL" in text:
            hints["inputType"] = "text"
            hints["mask"] = "99999"

        # Phone
        elif "PHONE" in text or "TELEPHONE" in text or "TEL" in text:
            hints["inputType"] = "tel"
            hints["mask"] = "(999) 999-9999"

        # Email
        elif "EMAIL" in text or "E-MAIL" in text:
            hints["inputType"] = "email"

        # Date
        elif "DATE" in text or "BIRTH" in text or "DOB" in text:
            hints["inputType"] = "date"

        # Currency
        elif "SALARY" in text or "AMOUNT" in text or "PRICE" in text or "COST" in text:
            hints["inputType"] = "number"
            hints["prefix"] = "$"

        # Number
        elif "AGE" in text or "QUANTITY" in text or "COUNT" in text:
            hints["inputType"] = "number"

        return hints


# ============================================================================
# SURVEYJS BUILDER (PHASE 6)
# ============================================================================

class SurveyJSBuilder:
    """
    Build optimal SurveyJS JSON from semantic groups.

    Features:
    - One panel per semantic group
    - Smart field naming with deduplication
    - Radio/checkbox grouping
    - Rich validators from TypeInferenceEngine
    - Progressive disclosure for multi-panel forms
    """

    def __init__(self, type_engine: TypeInferenceEngine):
        """
        Initialize builder.

        Args:
            type_engine: Type inference engine
        """
        self.type_engine = type_engine
        self.used_names: Dict[str, int] = {}

    def build_survey(
        self,
        groups: List[SemanticGroup],
        title: str
    ) -> Dict[str, Any]:
        """
        Build SurveyJS JSON from semantic groups.

        Args:
            groups: Semantic groups
            title: Form title

        Returns:
            SurveyJS JSON dictionary
        """
        logger.info(f"Building SurveyJS for '{title}'")

        # Build panels
        panels = []
        for group in groups:
            panel = self._build_panel(group)
            if panel:
                panels.append(panel)

        # Build survey JSON
        survey = {
            "title": self._prettify_title(title),
            "description": "Form generated from PDF",
            "showQuestionNumbers": "off",
            "pages": [
                {
                    "name": "page1",
                    "elements": panels
                }
            ]
        }

        # Add progress bar if many panels
        if len(panels) >= 3:
            survey["showProgressBar"] = "top"

        logger.info(f"Built survey with {len(panels)} panels")
        return survey

    def _build_panel(self, group: SemanticGroup) -> Optional[Dict[str, Any]]:
        """
        Build panel from semantic group.

        Args:
            group: Semantic group

        Returns:
            Panel dictionary or None
        """
        if not group.fields:
            return None

        # Build questions
        questions = []

        # Track radio fields
        radio_counts: Dict[str, int] = defaultdict(int)
        for field in group.fields:
            if field.field_type in (FieldType.RADIO, FieldType.PUSH_BUTTON):
                radio_counts[field.key] += 1

        # Track grouped checkboxes
        checkbox_fields = [f for f in group.fields if f.field_type == FieldType.CHECKBOX]
        grouped_checkboxes = self._group_checkboxes(checkbox_fields)
        used_checkbox_keys = {f.key for group in grouped_checkboxes for f in group}

        # Add grouped checkboxes first
        for checkbox_group in grouped_checkboxes:
            question = self._build_checkbox_group(checkbox_group)
            if question:
                questions.append(question)

        # Track emitted radios
        emitted_radios: Set[str] = set()

        # Add other questions
        for field in group.fields:
            # Skip already grouped checkboxes
            if field.key in used_checkbox_keys:
                continue

            # Handle radio groups
            if field.field_type in (FieldType.RADIO, FieldType.PUSH_BUTTON):
                if radio_counts[field.key] > 1:
                    if field.key in emitted_radios:
                        continue
                    # Build radio group
                    radio_fields = [f for f in group.fields if f.key == field.key]
                    question = self._build_radio_group(radio_fields)
                    emitted_radios.add(field.key)
                else:
                    # Single radio/button -> boolean
                    question = self._build_boolean_question(field)

            # Handle other field types
            elif field.field_type == FieldType.CHECKBOX:
                # Single checkbox -> boolean
                question = self._build_boolean_question(field)

            elif field.field_type in (FieldType.DROPDOWN, FieldType.LISTBOX):
                question = self._build_dropdown_question(field)

            elif field.field_type == FieldType.MULTILINE_TEXT:
                question = self._build_text_question(field, multiline=True)

            elif field.field_type == FieldType.SIGNATURE:
                question = self._build_signature_question(field)

            else:
                # Default: text question
                question = self._build_text_question(field, multiline=False)

            if question:
                questions.append(question)

        if not questions:
            return None

        # Build panel
        panel_name = self._slugify(group.title)
        panel = {
            "type": "panel",
            "name": self._unique_name(panel_name),
            "title": group.title,
            "elements": questions
        }

        return panel

    def _build_text_question(self, field: PDFField, multiline: bool = False) -> Dict[str, Any]:
        """Build text question."""
        question = {
            "type": "comment" if multiline else "text",
            "name": self._unique_name(field.key),
            "title": self._prettify_label(field.label)
        }

        # Add validators
        validators = self.type_engine.infer_validators(field)
        if validators:
            question["validators"] = [v.model_dump(exclude_none=True) for v in validators]

        # Add input hints
        hints = self.type_engine.infer_input_hints(field)
        question.update(hints)

        # Add common properties
        self._add_common_props(question, field)

        return question

    def _build_boolean_question(self, field: PDFField) -> Dict[str, Any]:
        """Build boolean question."""
        question = {
            "type": "boolean",
            "name": self._unique_name(field.key),
            "title": self._prettify_label(field.label)
        }

        self._add_common_props(question, field)
        return question

    def _build_dropdown_question(self, field: PDFField) -> Dict[str, Any]:
        """Build dropdown question."""
        question = {
            "type": "dropdown",
            "name": self._unique_name(field.key),
            "title": self._prettify_label(field.label)
        }

        # Add choices
        if field.options:
            question["choices"] = [
                {"value": opt, "text": self._prettify_label(opt)}
                for opt in field.options
            ]

        self._add_common_props(question, field)
        return question

    def _build_signature_question(self, field: PDFField) -> Dict[str, Any]:
        """Build signature question."""
        question = {
            "type": "signaturepad",
            "name": self._unique_name(field.key),
            "title": self._prettify_label(field.label)
        }

        self._add_common_props(question, field)
        return question

    def _build_radio_group(self, fields: List[PDFField]) -> Dict[str, Any]:
        """Build radio group from multiple radio fields."""
        if not fields:
            return {}

        first = fields[0]
        question = {
            "type": "radiogroup",
            "name": self._unique_name(first.key),
            "title": self._prettify_label(first.label)
        }

        # Extract choices from appearance states
        choices = self._extract_choices_from_appearance(fields)
        if choices:
            question["choices"] = choices

        # Find default value
        default = None
        for field in fields:
            if field.appearance_state:
                default = field.appearance_state
                break
        if not default and first.default_value:
            default = str(first.default_value).lstrip("/")

        if default:
            question["defaultValue"] = default

        self._add_common_props(question, first)
        return question

    def _build_checkbox_group(self, fields: List[PDFField]) -> Optional[Dict[str, Any]]:
        """Build checkbox group from multiple checkbox fields."""
        if len(fields) < 2:
            return None

        # Infer group title
        prefix = None
        if fields[0].key and "_" in fields[0].key:
            prefix = fields[0].key.split("_")[0]

        title = self._prettify_label(prefix) if prefix else "Selections"

        question = {
            "type": "checkbox",
            "name": self._unique_name(self._slugify(title)),
            "title": title,
            "choices": [
                {"value": f.key, "text": self._prettify_label(f.label)}
                for f in fields
            ]
        }

        # Find defaults
        defaults = []
        for field in fields:
            if field.default_value and str(field.default_value) not in ("", "/Off", "Off"):
                defaults.append(field.key)

        if defaults:
            question["defaultValue"] = defaults

        # Add common props from first field
        if any(f.required for f in fields):
            question["isRequired"] = True
        if any(f.read_only for f in fields):
            question["readOnly"] = True

        return question

    def _group_checkboxes(self, fields: List[PDFField]) -> List[List[PDFField]]:
        """
        Group related checkboxes spatially.

        Args:
            fields: Checkbox fields

        Returns:
            List of checkbox groups
        """
        if not fields:
            return []

        # Sort by position
        sorted_fields = sorted(
            fields,
            key=lambda f: (-f.bbox.y, f.bbox.x)
        )

        # Cluster by Y position
        groups: List[List[PDFField]] = []
        current_group: List[PDFField] = []

        for field in sorted_fields:
            if not current_group:
                current_group.append(field)
            else:
                # Check Y distance
                last = current_group[-1]
                y_dist = abs(field.bbox.y - last.bbox.y)

                if y_dist <= DEFAULT_EPS_VERTICAL:
                    current_group.append(field)
                else:
                    if len(current_group) >= 2:
                        groups.append(current_group)
                    current_group = [field]

        if len(current_group) >= 2:
            groups.append(current_group)

        return groups

    def _extract_choices_from_appearance(self, fields: List[PDFField]) -> List[Dict[str, str]]:
        """Extract choices from appearance states."""
        values: List[str] = []
        for field in fields:
            if field.appearance_states:
                for state in field.appearance_states:
                    if state not in values:
                        values.append(state)

        if not values:
            # Generate generic choices
            return [
                {"value": f"option_{i+1}", "text": f"Option {i+1}"}
                for i in range(len(fields))
            ]

        return [
            {"value": v, "text": self._prettify_label(v)}
            for v in values
        ]

    def _add_common_props(self, question: Dict[str, Any], field: PDFField) -> None:
        """Add common properties to question."""
        if field.required:
            question["isRequired"] = True

        if field.read_only:
            question["readOnly"] = True

        # Add default value
        if field.default_value is not None and field.default_value != "":
            default = field.default_value

            # Clean up default value
            if isinstance(default, str):
                if default.startswith("/"):
                    default = default.lstrip("/")
                if default in ("Off", "/Off"):
                    default = None

            if default is not None:
                if question["type"] == "boolean":
                    question["defaultValue"] = bool(default)
                else:
                    question["defaultValue"] = default

        # Add description from tooltip
        if field.tooltip and field.tooltip != field.label:
            question["description"] = field.tooltip

    def _unique_name(self, base: str) -> str:
        """Generate unique name with deduplication."""
        slug = self._slugify(base)

        if slug not in self.used_names:
            self.used_names[slug] = 1
            return slug

        self.used_names[slug] += 1
        return f"{slug}_{self.used_names[slug]}"

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to slug."""
        cleaned = []
        for ch in text.lower():
            if ch.isalnum():
                cleaned.append(ch)
            elif ch in (" ", "-", "_", "."):
                cleaned.append("_")
        slug = "_".join(filter(None, "".join(cleaned).split("_")))
        return slug or "field"

    @staticmethod
    def _prettify_label(text: str) -> str:
        """Prettify label for display."""
        if not text:
            return ""
        cleaned = " ".join(text.replace("_", " ").replace(".", " ").split())
        if cleaned.isupper() or "_" in text:
            return cleaned.title()
        return cleaned

    @staticmethod
    def _prettify_title(text: str) -> str:
        """Prettify form title."""
        # Remove .pdf extension
        if text.lower().endswith(".pdf"):
            text = text[:-4]
        return SurveyJSBuilder._prettify_label(text)


# ============================================================================
# PDF FORM PARSER (PHASE 7 - ORCHESTRATOR)
# ============================================================================

class PDFFormParser:
    """
    Main orchestrator for PDF form parsing.

    Coordinates all components with comprehensive error handling.
    """

    def __init__(
        self,
        eps_horizontal: float = DEFAULT_EPS_HORIZONTAL,
        eps_vertical: float = DEFAULT_EPS_VERTICAL
    ):
        """
        Initialize parser.

        Args:
            eps_horizontal: Horizontal clustering threshold
            eps_vertical: Vertical clustering threshold
        """
        self.extractor = PDFExtractor()
        self.layout_analyzer = LayoutAnalyzer(eps_horizontal, eps_vertical)
        self.semantic_grouper = SemanticGrouper()
        self.type_engine = TypeInferenceEngine()
        self.surveyjs_builder = SurveyJSBuilder(self.type_engine)

    def parse_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Parse a PDF form.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dictionary with fields, groups, and surveyjs JSON

        Raises:
            Exception: If parsing fails
        """
        logger.info(f"Parsing PDF: {pdf_path.name}")

        try:
            # Phase 1: Extract fields
            fields = self.extractor.extract_fields(pdf_path)

            if not fields:
                logger.warning(f"No fields found in {pdf_path.name}")
                return {
                    "file": pdf_path.name,
                    "fields": [],
                    "groups": [],
                    "surveyjs": self._empty_survey(pdf_path.name)
                }

            # Phase 2: Analyze layout
            clusters = self.layout_analyzer.analyze_layout(fields)

            # Phase 3: Semantic grouping
            groups = self.semantic_grouper.group_fields(fields, clusters)

            # Phase 4: Build SurveyJS
            surveyjs = self.surveyjs_builder.build_survey(groups, pdf_path.name)

            # Prepare output
            result = {
                "file": pdf_path.name,
                "fields": [self._field_to_dict(f) for f in fields],
                "groups": [self._group_to_dict(g) for g in groups],
                "surveyjs": surveyjs
            }

            logger.info(f"Successfully parsed {pdf_path.name}")
            return result

        except Exception as e:
            logger.error(f"Failed to parse {pdf_path.name}: {e}", exc_info=True)
            raise

    def _field_to_dict(self, field: PDFField) -> Dict[str, Any]:
        """Convert PDFField to dictionary."""
        return {
            "key": field.key,
            "label": field.label,
            "type": field.field_type.value,
            "x": field.bbox.x,
            "y": field.bbox.y,
            "width": field.bbox.width,
            "height": field.bbox.height,
            "page": field.bbox.page,
            "default_value": field.default_value,
            "required": field.required,
            "read_only": field.read_only,
            "options": field.options,
            "appearance_states": field.appearance_states,
            "appearance_state": field.appearance_state,
            "group_path": field.group_path
        }

    def _group_to_dict(self, group: SemanticGroup) -> Dict[str, Any]:
        """Convert SemanticGroup to dictionary."""
        return {
            "title": group.title,
            "field_count": len(group.fields),
            "field_keys": [f.key for f in group.fields],
            "prefix": group.prefix,
            "confidence": group.confidence,
            "relationships": group.relationships,
            "page": group.page
        }

    def _empty_survey(self, filename: str) -> Dict[str, Any]:
        """Create empty survey JSON."""
        return {
            "title": self.surveyjs_builder._prettify_title(filename),
            "description": "No fields found in form",
            "showQuestionNumbers": "off",
            "pages": [{"name": "page1", "elements": []}]
        }


# ============================================================================
# CLI & OUTPUT (PHASE 8)
# ============================================================================

def gather_pdfs(root: Path, patterns: List[str]) -> List[Path]:
    """
    Gather PDF files matching patterns.

    Args:
        root: Root directory
        patterns: Glob patterns

    Returns:
        List of unique PDF paths
    """
    pdfs: List[Path] = []

    if patterns:
        for pattern in patterns:
            pdfs.extend(sorted(root.glob(pattern)))
    else:
        pdfs = sorted(root.glob("*.pdf"))

    # Deduplicate
    seen = set()
    unique = []
    for p in pdfs:
        resolved = p.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(p)

    return unique


def write_outputs(
    results: List[Dict[str, Any]],
    out_file: str,
    pretty: bool,
    per_file_out: Optional[str],
    surveyjs_out: Optional[str]
) -> None:
    """
    Write output files.

    Args:
        results: Parsing results
        out_file: Main output file
        pretty: Pretty print JSON
        per_file_out: Per-file output directory
        surveyjs_out: SurveyJS output directory
    """
    # Prepare JSON dump options
    if HAS_ORJSON:
        def dump_json(data: Any, file_path: Path) -> None:
            options = orjson.OPT_INDENT_2 if pretty else 0
            with open(file_path, "wb") as f:
                f.write(orjson.dumps(data, option=options))
    else:
        def dump_json(data: Any, file_path: Path) -> None:
            indent = 2 if pretty else None
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)

    # Write main index
    dump_json({"forms": results}, Path(out_file))
    logger.info(f"Wrote {len(results)} form(s) to {out_file}")

    # Write per-file outputs
    if per_file_out:
        out_dir = Path(per_file_out)
        out_dir.mkdir(parents=True, exist_ok=True)

        for result in results:
            filename = Path(result["file"]).stem
            out_path = out_dir / f"{filename}.json"
            dump_json(result, out_path)

        logger.info(f"Wrote per-file outputs to {out_dir}")

    # Write SurveyJS outputs
    if surveyjs_out:
        out_dir = Path(surveyjs_out)
        out_dir.mkdir(parents=True, exist_ok=True)

        for result in results:
            filename = Path(result["file"]).stem
            out_path = out_dir / f"{filename}.surveyjs.json"
            dump_json(result["surveyjs"], out_path)

        logger.info(f"Wrote SurveyJS outputs to {out_dir}")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="World-Class PDF Form Parser - Extract and convert PDF forms to SurveyJS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --glob "*.pdf" --surveyjs-out ./output --pretty
  %(prog)s --glob "forms/*.pdf" --out results.json --verbose
  %(prog)s --glob "*.pdf" --per-file-out ./json --surveyjs-out ./survey
        """
    )

    parser.add_argument(
        "--glob",
        action="append",
        default=[],
        help="Glob pattern(s) for PDFs (default: *.pdf). Can be specified multiple times."
    )
    parser.add_argument(
        "--out",
        default="forms_index.json",
        help="Output JSON file (default: forms_index.json)"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output"
    )
    parser.add_argument(
        "--per-file-out",
        default=None,
        help="Optional output directory for per-file JSON"
    )
    parser.add_argument(
        "--surveyjs-out",
        default=None,
        help="Optional output directory for per-file SurveyJS JSON"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level)"
    )
    parser.add_argument(
        "--eps-horizontal",
        type=float,
        default=DEFAULT_EPS_HORIZONTAL,
        help=f"Horizontal clustering threshold (default: {DEFAULT_EPS_HORIZONTAL})"
    )
    parser.add_argument(
        "--eps-vertical",
        type=float,
        default=DEFAULT_EPS_VERTICAL,
        help=f"Vertical clustering threshold (default: {DEFAULT_EPS_VERTICAL})"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Gather PDFs
    root = Path.cwd()
    pdfs = gather_pdfs(root, args.glob)

    if not pdfs:
        logger.error("No PDF files found")
        raise SystemExit("No PDF files found.")

    logger.info(f"Found {len(pdfs)} PDF file(s)")

    # Initialize parser
    form_parser = PDFFormParser(
        eps_horizontal=args.eps_horizontal,
        eps_vertical=args.eps_vertical
    )

    # Parse all PDFs
    results = []
    for pdf_path in pdfs:
        try:
            result = form_parser.parse_pdf(pdf_path)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to parse {pdf_path.name}: {e}")
            # Continue with other PDFs
            continue

    if not results:
        logger.error("No PDFs successfully parsed")
        raise SystemExit("No PDFs successfully parsed.")

    # Write outputs
    write_outputs(
        results,
        args.out,
        args.pretty,
        args.per_file_out,
        args.surveyjs_out
    )

    print(f"\nSuccessfully processed {len(results)} form(s)")
    print(f"Output written to: {args.out}")

    if args.per_file_out:
        print(f"Per-file JSON: {args.per_file_out}/")
    if args.surveyjs_out:
        print(f"SurveyJS JSON: {args.surveyjs_out}/")


if __name__ == "__main__":
    main()
