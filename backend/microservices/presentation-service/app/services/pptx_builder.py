"""
PPTX Builder

Generates PowerPoint presentations using python-pptx library.
Supports external .pptx templates with rich visual designs.

Template Strategy (based on PPTAgent research):
- Templates contain pre-designed SLIDES with visual elements (backgrounds, shapes, images)
- Layouts (slide masters) are often empty/basic - the design is on the slides themselves
- We DUPLICATE existing template slides to preserve all visual elements
- Then we modify ONLY the text content, preserving the original styling

This approach achieves 95%+ design preservation (per PPTAgent paper, 2025).

Template Setup:
1. Download a .pptx template with designed slides
2. Place it in /templates/ directory with name: {template_name}.pptx
3. The builder will duplicate and modify slides preserving the design
"""
import copy
import io
import logging
import os
from typing import List, Optional, Tuple, Dict, Any

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.opc.constants import RELATIONSHIP_TYPE as RT

from app.core.config import settings
from app.schemas import SlideOutline, SlideType, PresentationConfig

logger = logging.getLogger(__name__)


# Layout type indices (standard PowerPoint layout order)
LAYOUT_TITLE_SLIDE = 0          # Title Slide
LAYOUT_TITLE_CONTENT = 1        # Title and Content
LAYOUT_SECTION_HEADER = 2       # Section Header
LAYOUT_TWO_CONTENT = 3          # Two Content
LAYOUT_COMPARISON = 4           # Comparison
LAYOUT_TITLE_ONLY = 5           # Title Only
LAYOUT_BLANK = 6                # Blank
LAYOUT_CONTENT_WITH_CAPTION = 7 # Content with Caption
LAYOUT_PICTURE_WITH_CAPTION = 8 # Picture with Caption

# Layout name patterns to search for (in order of preference)
TITLE_SLIDE_PATTERNS = ["title slide", "título", "portada", "cover", "title"]
CONTENT_SLIDE_PATTERNS = ["title and content", "título y contenido", "content", "bullets", "body"]
SECTION_SLIDE_PATTERNS = ["section", "sección", "header", "divider"]
CLOSING_SLIDE_PATTERNS = ["thank", "gracias", "closing", "end", "final"]

# Fallback color schemes (used when no template file exists)
TEMPLATE_COLORS = {
    "corporate": {
        "title_bg": RGBColor(0x00, 0x5A, 0x9C),
        "title_text": RGBColor(0xFF, 0xFF, 0xFF),
        "content_bg": RGBColor(0xFF, 0xFF, 0xFF),
        "content_text": RGBColor(0x33, 0x33, 0x33),
        "accent": RGBColor(0x00, 0x5A, 0x9C),
    },
    "educational": {
        "title_bg": RGBColor(0x2E, 0x7D, 0x32),
        "title_text": RGBColor(0xFF, 0xFF, 0xFF),
        "content_bg": RGBColor(0xFF, 0xFF, 0xFF),
        "content_text": RGBColor(0x33, 0x33, 0x33),
        "accent": RGBColor(0x2E, 0x7D, 0x32),
    },
    "minimal": {
        "title_bg": RGBColor(0xF5, 0xF5, 0xF5),
        "title_text": RGBColor(0x21, 0x21, 0x21),
        "content_bg": RGBColor(0xFF, 0xFF, 0xFF),
        "content_text": RGBColor(0x42, 0x42, 0x42),
        "accent": RGBColor(0x75, 0x75, 0x75),
    },
    "creative": {
        "title_bg": RGBColor(0x7B, 0x1F, 0xA2),
        "title_text": RGBColor(0xFF, 0xFF, 0xFF),
        "content_bg": RGBColor(0xFF, 0xFF, 0xFF),
        "content_text": RGBColor(0x33, 0x33, 0x33),
        "accent": RGBColor(0x7B, 0x1F, 0xA2),
    },
    "nouxcube": {
        "title_bg": RGBColor(0x1E, 0x3A, 0x5F),
        "title_text": RGBColor(0xFF, 0xFF, 0xFF),
        "content_bg": RGBColor(0xFF, 0xFF, 0xFF),
        "content_text": RGBColor(0x1E, 0x3A, 0x5F),
        "accent": RGBColor(0x4A, 0x90, 0xD9),
    },
}


class PPTXBuilder:
    """
    Builds PowerPoint presentations from slide outlines.

    Supports two modes:
    1. Template mode: Uses .pptx template files with professional layouts
    2. Fallback mode: Creates slides programmatically with color schemes
    """

    def __init__(self):
        self.templates_dir = settings.templates_dir
        self._using_template = False
        self._layout_cache: Dict[str, Any] = {}

    def build_presentation(
        self,
        outlines: List[SlideOutline],
        config: PresentationConfig,
    ) -> Tuple[bytes, int]:
        """
        Build a PowerPoint presentation from slide outlines.

        Args:
            outlines: List of slide outlines
            config: Presentation configuration

        Returns:
            Tuple of (PPTX bytes, slide count)
        """
        # Load template or create blank
        prs, self._using_template = self._load_template(config.template)

        # Cache available layouts
        self._cache_layouts(prs)

        # Get color scheme (only used in fallback mode)
        colors = TEMPLATE_COLORS.get(config.template, TEMPLATE_COLORS["corporate"])

        logger.info(
            f"Building presentation: {len(outlines)} slides, "
            f"template: {config.template}, using_template_file: {self._using_template}"
        )

        # Log available layouts for debugging
        if self._using_template:
            logger.info(f"Available layouts: {list(self._layout_cache.keys())}")
            logger.info(f"Template has {len(prs.slides)} existing slides")

        # Strategy depends on whether we have a template with designed slides
        if self._using_template and len(prs.slides) > 0:
            # Template mode: preserve template design by modifying/duplicating existing slides
            self._build_from_template_slides(prs, outlines, config.include_speaker_notes)
        else:
            # Fallback mode: create slides programmatically
            for outline in outlines:
                slide_type = outline.slide_type

                if outline.slide_number == 1 or slide_type == SlideType.TITLE:
                    self._add_title_slide(prs, outline, colors)
                elif slide_type == SlideType.CLOSING or outline.slide_number == len(outlines):
                    self._add_closing_slide(prs, outline, colors)
                elif slide_type == SlideType.SECTION:
                    self._add_section_slide(prs, outline, colors)
                else:
                    self._add_content_slide(prs, outline, colors, config.include_speaker_notes)

        # Save to bytes
        pptx_bytes = io.BytesIO()
        prs.save(pptx_bytes)
        pptx_bytes.seek(0)

        slide_count = len(prs.slides)
        logger.info(f"Built presentation with {slide_count} slides")

        return pptx_bytes.getvalue(), slide_count

    def _load_template(self, template_name: str) -> Tuple[Presentation, bool]:
        """
        Load a template or create a blank presentation.

        Returns:
            Tuple of (Presentation, is_using_template_file)
        """
        template_path = os.path.join(self.templates_dir, f"{template_name}.pptx")

        if os.path.exists(template_path):
            logger.info(f"Loading template file: {template_path}")
            return Presentation(template_path), True
        else:
            # Try to find any template file as fallback
            if os.path.exists(self.templates_dir):
                available = [f for f in os.listdir(self.templates_dir) if f.endswith('.pptx')]
                if available:
                    fallback_path = os.path.join(self.templates_dir, available[0])
                    logger.info(f"Template '{template_name}' not found, using fallback: {fallback_path}")
                    return Presentation(fallback_path), True

            logger.info(f"No template files found, creating blank presentation")
            return Presentation(), False

    def _cache_layouts(self, prs: Presentation):
        """Cache available layouts from the presentation for quick lookup."""
        self._layout_cache = {}

        for idx, layout in enumerate(prs.slide_layouts):
            layout_name = layout.name.lower() if layout.name else f"layout_{idx}"
            self._layout_cache[layout_name] = {
                "index": idx,
                "layout": layout,
                "name": layout.name,
            }
            logger.debug(f"Cached layout [{idx}]: {layout.name}")

    def _find_layout(self, prs: Presentation, patterns: List[str], fallback_index: int) -> Any:
        """
        Find a layout matching any of the given patterns.

        Args:
            prs: Presentation object
            patterns: List of name patterns to search (in order of preference)
            fallback_index: Index to use if no pattern matches

        Returns:
            SlideLayout object
        """
        # Search by pattern
        for pattern in patterns:
            for name, info in self._layout_cache.items():
                if pattern in name:
                    logger.debug(f"Found layout '{info['name']}' matching pattern '{pattern}'")
                    return info["layout"]

        # Fallback to index
        try:
            return prs.slide_layouts[fallback_index]
        except IndexError:
            return prs.slide_layouts[0]

    def _duplicate_slide(self, prs: Presentation, source_index: int) -> Any:
        """
        Duplicate a slide preserving ALL visual elements (backgrounds, shapes, images).

        This workaround uses deepcopy on XML elements, which is the recommended
        approach since python-pptx doesn't have a native Slide.duplicate() method.

        Based on: https://gist.github.com/robintw/3df1464e5c8a7ee8835e
        and python-pptx Issue #132

        Args:
            prs: Presentation object
            source_index: Index of the slide to duplicate

        Returns:
            The new duplicated slide
        """
        source = prs.slides[source_index]

        # Use the SAME layout as the source slide to maintain consistency
        # This avoids duplicate relationship issues
        dest = prs.slides.add_slide(source.slide_layout)

        # Remove all shapes that were added from the layout (we'll copy from source)
        # We need to keep the slide structure but replace shapes
        for shape in list(dest.shapes):
            sp = shape.element
            sp.getparent().remove(sp)

        # Copy all shapes from source to destination using deepcopy
        for shape in source.shapes:
            el = shape.element
            new_el = copy.deepcopy(el)
            dest.shapes._spTree.insert_element_before(new_el, 'p:extLst')

        # Copy image/media relationships (not slideLayout which is already set)
        for rel_id, rel in source.part.rels.items():
            reltype = rel.reltype
            # Only copy media relationships, not structural ones
            if any(x in reltype for x in ["image", "media", "chart"]):
                try:
                    dest.part.relate_to(rel._target, reltype)
                except Exception as e:
                    logger.debug(f"Could not copy relationship {rel_id}: {e}")

        logger.debug(f"Duplicated slide {source_index} with {len(source.shapes)} shapes")
        return dest

    def _build_from_template_slides(
        self,
        prs: Presentation,
        outlines: List[SlideOutline],
        include_notes: bool
    ):
        """
        Build presentation using HYBRID approach:
        1. Create slides from LAYOUTS (proper placeholders for variable content)
        2. Copy DECORATIVE elements from template slides (images, backgrounds)

        This gives us:
        - Flexible content handling (layouts have auto-sizing placeholders)
        - Rich visual design (decorations copied from template slides)
        """
        template_slides = list(prs.slides)
        num_template_slides = len(template_slides)

        logger.info(f"Building with hybrid approach: {len(outlines)} outlines, {num_template_slides} template slides")

        # Find best layouts for each slide type
        title_layout = self._find_layout(prs, TITLE_SLIDE_PATTERNS, LAYOUT_TITLE_SLIDE)
        content_layout = self._find_layout(prs, CONTENT_SLIDE_PATTERNS, LAYOUT_TITLE_CONTENT)
        section_layout = self._find_layout(prs, SECTION_SLIDE_PATTERNS, LAYOUT_SECTION_HEADER)

        # Identify reference slides for decorations (if template has designed slides)
        # Usually: slide 0 = title, slides with TITLE_AND_BODY layout = content
        title_ref_slide = template_slides[0] if num_template_slides > 0 else None
        content_ref_slide = None
        for slide in template_slides:
            if slide.slide_layout.name in ["TITLE_AND_BODY", "ONE_COLUMN_TEXT"]:
                content_ref_slide = slide
                break
        if not content_ref_slide and num_template_slides > 1:
            content_ref_slide = template_slides[1]

        logger.info(f"Reference slides - Title: {title_ref_slide is not None}, Content: {content_ref_slide is not None}")

        # Remove all existing template slides (we'll create fresh ones)
        self._clear_template_slides(prs)

        # Create slides for each outline
        for i, outline in enumerate(outlines):
            slide_type = outline.slide_type

            if i == 0 or slide_type == SlideType.TITLE:
                # Title slide
                slide = prs.slides.add_slide(title_layout)
                self._copy_decorations(title_ref_slide, slide)
                self._fill_title_slide(slide, outline)
                logger.debug(f"Created title slide: '{outline.title[:30]}...'")

            elif slide_type == SlideType.SECTION:
                # Section divider
                slide = prs.slides.add_slide(section_layout)
                self._fill_section_slide(slide, outline)
                logger.debug(f"Created section slide: '{outline.title[:30]}...'")

            else:
                # Content slide
                slide = prs.slides.add_slide(content_layout)
                self._copy_decorations(content_ref_slide, slide)
                self._fill_content_slide(slide, outline)
                logger.debug(f"Created content slide: '{outline.title[:30]}...'")

            # Add speaker notes if requested
            if include_notes and outline.speaker_notes:
                try:
                    slide.notes_slide.notes_text_frame.text = outline.speaker_notes
                except Exception as e:
                    logger.debug(f"Could not add notes to slide {i}: {e}")

    def _copy_decorations(self, source_slide, dest_slide):
        """
        Copy non-placeholder decorative elements from source to destination.

        Copies: images, autoshapes (backgrounds, lines), but NOT placeholders.
        This preserves visual design while keeping placeholders for content.
        """
        if not source_slide:
            return

        for shape in source_slide.shapes:
            # Skip placeholders - dest slide already has its own
            if shape.is_placeholder:
                continue

            # Skip text boxes that might contain template instructions
            if shape.has_text_frame:
                text = shape.text_frame.text.lower() if shape.text_frame.text else ""
                # Skip if it looks like instruction text
                if any(p in text for p in ["open this", "click", "download", "slides"]):
                    continue

            # Copy the shape using deepcopy
            try:
                el = shape.element
                new_el = copy.deepcopy(el)
                dest_slide.shapes._spTree.insert_element_before(new_el, 'p:extLst')

                # Copy image relationships if needed
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    for rel_id, rel in source_slide.part.rels.items():
                        if "image" in rel.reltype:
                            try:
                                dest_slide.part.relate_to(rel._target, rel.reltype)
                            except Exception:
                                pass
            except Exception as e:
                logger.debug(f"Could not copy decoration {shape.name}: {e}")

    def _fill_title_slide(self, slide, outline: SlideOutline):
        """Fill a title slide's placeholders with content."""
        PH_TITLE = 1
        PH_CENTER_TITLE = 3
        PH_SUBTITLE = 4

        for shape in slide.placeholders:
            ph_type = shape.placeholder_format.type
            if ph_type in (PH_TITLE, PH_CENTER_TITLE):
                shape.text = outline.title
            elif ph_type == PH_SUBTITLE:
                if outline.bullet_points:
                    shape.text = outline.bullet_points[0]

    def _fill_content_slide(self, slide, outline: SlideOutline):
        """Fill a content slide's placeholders with content."""
        PH_TITLE = 1
        PH_BODY = 2

        for shape in slide.placeholders:
            ph_type = shape.placeholder_format.type
            if ph_type == PH_TITLE:
                shape.text = outline.title
            elif ph_type == PH_BODY and outline.bullet_points:
                tf = shape.text_frame
                tf.clear()
                for i, point in enumerate(outline.bullet_points):
                    if i == 0:
                        para = tf.paragraphs[0]
                    else:
                        para = tf.add_paragraph()
                    para.text = point
                    para.level = 0

    def _fill_section_slide(self, slide, outline: SlideOutline):
        """Fill a section slide's placeholders."""
        for shape in slide.placeholders:
            ph_type = shape.placeholder_format.type
            if ph_type in (1, 3):  # TITLE or CENTER_TITLE
                shape.text = outline.title
                break

    def _modify_slide_text(self, slide, title: str, body: str):
        """
        Modify text content in an existing slide, preserving visual design.

        Strategy (Priority Order):
        1. Use PLACEHOLDER types (TITLE=1, BODY=2, CENTER_TITLE=3) - most reliable
        2. Use shape NAMES containing 'title', 'body', 'content' - second choice
        3. Use position-based detection - fallback only

        This ensures we modify the correct shapes even with complex slide designs.
        """
        # Placeholder type constants (from pptx.enum.shapes.PP_PLACEHOLDER_TYPE)
        PH_TITLE = 1           # TITLE
        PH_BODY = 2            # BODY
        PH_CENTER_TITLE = 3    # CENTER_TITLE
        PH_SUBTITLE = 4        # SUBTITLE
        PH_SLIDE_NUMBER = 13   # SLIDE_NUMBER - skip this

        # Patterns that indicate template instruction text to clear
        CLEAR_PATTERNS = [
            "open this document", "google slides", "click on", "click here",
            "download", "edit this", "replace this", "your text here",
            "lorem ipsum", "slidespower", "further information",
            "instructions for use", "to get a good presentation",
        ]

        # First pass: Identify shapes by type
        title_placeholder = None
        body_placeholder = None
        title_by_name = None
        body_by_name = None
        other_text_shapes = []

        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue

            # Check if it's a placeholder
            if shape.is_placeholder:
                ph_type = shape.placeholder_format.type
                # Skip slide number placeholders
                if ph_type == PH_SLIDE_NUMBER:
                    continue
                # Title placeholders
                if ph_type in (PH_TITLE, PH_CENTER_TITLE) and not title_placeholder:
                    title_placeholder = shape
                    logger.debug(f"Found TITLE placeholder: {shape.name}")
                # Body/content placeholders
                elif ph_type in (PH_BODY, PH_SUBTITLE) and not body_placeholder:
                    body_placeholder = shape
                    logger.debug(f"Found BODY placeholder: {shape.name}")
            else:
                # Check by name
                name_lower = shape.name.lower() if shape.name else ""
                if any(x in name_lower for x in ["title", "título"]) and not title_by_name:
                    title_by_name = shape
                elif any(x in name_lower for x in ["body", "content", "texto", "cuerpo"]) and not body_by_name:
                    body_by_name = shape
                else:
                    other_text_shapes.append(shape)

        # Determine which shapes to use (priority: placeholder > name > position)
        title_shape = title_placeholder or title_by_name
        body_shape = body_placeholder or body_by_name

        # Fallback to position-based if no semantic matches
        if not title_shape or not body_shape:
            TITLE_AREA_THRESHOLD = 1400000  # ~1.5 inches in EMUs
            position_title = []
            position_body = []

            shapes_to_check = other_text_shapes
            if not title_shape:
                shapes_to_check = [s for s in slide.shapes if s.has_text_frame and s != body_shape]
            if not body_shape:
                shapes_to_check = [s for s in slide.shapes if s.has_text_frame and s != title_shape]

            for shape in shapes_to_check:
                if shape.is_placeholder and shape.placeholder_format.type == PH_SLIDE_NUMBER:
                    continue
                try:
                    top = shape.top.emu if shape.top else 0
                except Exception:
                    top = 0

                if top < TITLE_AREA_THRESHOLD:
                    position_title.append((top, shape))
                else:
                    position_body.append((top, shape))

            if not title_shape and position_title:
                position_title.sort(key=lambda x: x[0])
                title_shape = position_title[0][1]
                logger.debug(f"Using position-based title: {title_shape.name}")

            if not body_shape and position_body:
                position_body.sort(key=lambda x: x[0])
                body_shape = position_body[0][1]
                logger.debug(f"Using position-based body: {body_shape.name}")

        # Set title content
        title_set = False
        if title_shape:
            self._set_text_preserving_style(title_shape.text_frame, title, is_title=True)
            title_set = True
            logger.debug(f"Set title in: {title_shape.name}")

        # Set body content
        body_set = False
        if body_shape and body:
            # Check if body has instruction text that needs clearing
            current_text = body_shape.text_frame.text.lower() if body_shape.text_frame.text else ""
            if any(pattern in current_text for pattern in CLEAR_PATTERNS):
                body_shape.text_frame.clear()
            self._set_text_preserving_style(body_shape.text_frame, body, is_title=False)
            body_set = True
            logger.debug(f"Set body in: {body_shape.name}")

        # Clear remaining instruction text in other shapes
        for shape in slide.shapes:
            if not shape.has_text_frame or shape == title_shape or shape == body_shape:
                continue
            current_text = shape.text_frame.text.lower() if shape.text_frame.text else ""
            if any(pattern in current_text for pattern in CLEAR_PATTERNS):
                shape.text_frame.clear()
                logger.debug(f"Cleared instruction text in: {shape.name}")

        if not title_set:
            logger.warning(f"Could not find title area in slide")
        if body and not body_set:
            logger.warning(f"Could not find body area in slide")

    def _set_text_preserving_style(self, text_frame, text: str, is_title: bool):
        """
        Set text in a text frame while preserving the original font styling.

        This is crucial for template preservation - we keep:
        - Font family
        - Font size
        - Font color
        - Bold/italic settings
        - Alignment
        - Bullet formatting for body text
        """
        if not text_frame.paragraphs:
            return

        # For titles, just set the first paragraph
        if is_title:
            para = text_frame.paragraphs[0]
            # Store original formatting
            original_font = para.font
            original_size = original_font.size
            original_bold = original_font.bold
            original_color = None
            try:
                original_color = original_font.color.rgb
            except:
                pass

            # Set text
            para.text = text

            # Restore formatting if it was lost
            if original_size:
                para.font.size = original_size
            if original_bold is not None:
                para.font.bold = original_bold
            if original_color:
                try:
                    para.font.color.rgb = original_color
                except:
                    pass
        else:
            # For body, handle multiple lines as formatted bullet points
            lines = text.split('\n') if text else []

            # Get original formatting from first paragraph
            first_para = text_frame.paragraphs[0]
            original_size = first_para.font.size or Pt(22)
            original_color = None
            try:
                original_color = first_para.font.color.rgb
            except:
                pass

            # Clear and rebuild with proper bullet formatting
            text_frame.clear()

            for i, line in enumerate(lines):
                if i == 0:
                    para = text_frame.paragraphs[0]
                else:
                    para = text_frame.add_paragraph()

                # Clean up the line text
                clean_line = line.strip()
                # Remove any existing bullet characters
                if clean_line.startswith(('•', '-', '*', '●', '○')):
                    clean_line = clean_line[1:].strip()

                para.text = clean_line
                para.level = 0  # Level 0 = first-level bullet

                # Apply formatting
                para.font.size = original_size
                if original_color:
                    try:
                        para.font.color.rgb = original_color
                    except:
                        pass

                # Add proper spacing for readability
                para.space_before = Pt(8)
                para.space_after = Pt(4)

    def _format_bullets(self, bullet_points: List[str]) -> str:
        """Format bullet points as newline-separated text."""
        return '\n'.join(bullet_points) if bullet_points else ""

    def _clear_template_slides(self, prs: Presentation):
        """Remove any existing slides from the template."""
        # Delete slides in reverse order to avoid index issues
        for i in range(len(prs.slides) - 1, -1, -1):
            rId = prs.slides._sldIdLst[i].rId
            prs.part.drop_rel(rId)
            del prs.slides._sldIdLst[i]

    def _add_title_slide(
        self,
        prs: Presentation,
        outline: SlideOutline,
        colors: dict,
    ):
        """Add a title slide using template layout or fallback."""
        if self._using_template:
            self._add_title_slide_from_template(prs, outline)
        else:
            self._add_title_slide_fallback(prs, outline, colors)

    def _add_title_slide_from_template(self, prs: Presentation, outline: SlideOutline):
        """Add title slide using template's title layout."""
        layout = self._find_layout(prs, TITLE_SLIDE_PATTERNS, LAYOUT_TITLE_SLIDE)
        slide = prs.slides.add_slide(layout)

        # Find and fill placeholders
        title_set = False
        subtitle_set = False

        for shape in slide.placeholders:
            placeholder_type = shape.placeholder_format.type
            logger.debug(f"Title slide placeholder: idx={shape.placeholder_format.idx}, type={placeholder_type}")

            # Title placeholder (type 1 = CENTER_TITLE, type 2 = TITLE)
            if placeholder_type in (1, 2) and not title_set:
                shape.text = outline.title
                title_set = True
            # Subtitle placeholder (type 3 = BODY, type 4 = CENTER_BODY, type 6 = SUBTITLE)
            elif placeholder_type in (3, 4, 6) and not subtitle_set:
                if outline.bullet_points:
                    shape.text = outline.bullet_points[0]
                subtitle_set = True

        # Fallback: if no placeholders found, add text boxes
        if not title_set:
            self._add_centered_title(slide, outline.title, Inches(2.5), Pt(44))
        if not subtitle_set and outline.bullet_points:
            self._add_centered_title(slide, outline.bullet_points[0], Inches(4.2), Pt(24))

    def _add_title_slide_fallback(self, prs: Presentation, outline: SlideOutline, colors: dict):
        """Add title slide with programmatic styling (no template)."""
        blank_layout = prs.slide_layouts[LAYOUT_BLANK] if len(prs.slide_layouts) > LAYOUT_BLANK else prs.slide_layouts[0]
        slide = prs.slides.add_slide(blank_layout)

        # Add background color
        background = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(10), Inches(7.5))
        background.fill.solid()
        background.fill.fore_color.rgb = colors["title_bg"]
        background.line.fill.background()

        # Add title
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(2.5), Inches(9), Inches(1.5))
        title_frame = title_box.text_frame
        title_para = title_frame.paragraphs[0]
        title_para.text = outline.title
        title_para.font.size = Pt(44)
        title_para.font.bold = True
        title_para.font.color.rgb = colors["title_text"]
        title_para.alignment = PP_ALIGN.CENTER

        # Add subtitle
        if outline.bullet_points:
            subtitle_box = slide.shapes.add_textbox(Inches(0.5), Inches(4.2), Inches(9), Inches(1))
            subtitle_frame = subtitle_box.text_frame
            subtitle_para = subtitle_frame.paragraphs[0]
            subtitle_para.text = outline.bullet_points[0]
            subtitle_para.font.size = Pt(24)
            subtitle_para.font.color.rgb = colors["title_text"]
            subtitle_para.alignment = PP_ALIGN.CENTER

    def _add_content_slide(
        self,
        prs: Presentation,
        outline: SlideOutline,
        colors: dict,
        include_notes: bool,
    ):
        """Add a content slide using template layout or fallback."""
        if self._using_template:
            self._add_content_slide_from_template(prs, outline, include_notes)
        else:
            self._add_content_slide_fallback(prs, outline, colors, include_notes)

    def _add_content_slide_from_template(self, prs: Presentation, outline: SlideOutline, include_notes: bool):
        """Add content slide using template's content layout."""
        layout = self._find_layout(prs, CONTENT_SLIDE_PATTERNS, LAYOUT_TITLE_CONTENT)
        slide = prs.slides.add_slide(layout)

        title_set = False
        content_set = False

        for shape in slide.placeholders:
            placeholder_type = shape.placeholder_format.type
            logger.debug(f"Content slide placeholder: idx={shape.placeholder_format.idx}, type={placeholder_type}")

            # Title placeholder
            if placeholder_type in (1, 2) and not title_set:
                shape.text = outline.title
                title_set = True
            # Body/content placeholder
            elif placeholder_type in (3, 7) and not content_set and outline.bullet_points:
                tf = shape.text_frame
                tf.clear()
                for i, point in enumerate(outline.bullet_points):
                    if i == 0:
                        p = tf.paragraphs[0]
                    else:
                        p = tf.add_paragraph()
                    p.text = point
                    p.level = 0
                content_set = True

        # Fallback if placeholders not found
        if not title_set:
            self._add_centered_title(slide, outline.title, Inches(0.5), Pt(32))
        if not content_set and outline.bullet_points:
            self._add_bullet_content(slide, outline.bullet_points, Inches(1.5))

        # Add speaker notes
        if include_notes and outline.speaker_notes:
            notes_slide = slide.notes_slide
            notes_slide.notes_text_frame.text = outline.speaker_notes

    def _add_content_slide_fallback(self, prs: Presentation, outline: SlideOutline, colors: dict, include_notes: bool):
        """Add content slide with programmatic styling (no template)."""
        blank_layout = prs.slide_layouts[LAYOUT_BLANK] if len(prs.slide_layouts) > LAYOUT_BLANK else prs.slide_layouts[0]
        slide = prs.slides.add_slide(blank_layout)

        # Title bar
        title_bar = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(10), Inches(1.2))
        title_bar.fill.solid()
        title_bar.fill.fore_color.rgb = colors["title_bg"]
        title_bar.line.fill.background()

        # Title text
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(0.8))
        title_para = title_box.text_frame.paragraphs[0]
        title_para.text = outline.title
        title_para.font.size = Pt(32)
        title_para.font.bold = True
        title_para.font.color.rgb = colors["title_text"]

        # Bullet points
        if outline.bullet_points:
            content_box = slide.shapes.add_textbox(Inches(0.75), Inches(1.7), Inches(8.5), Inches(5))
            content_frame = content_box.text_frame
            content_frame.word_wrap = True

            for i, point in enumerate(outline.bullet_points):
                para = content_frame.paragraphs[0] if i == 0 else content_frame.add_paragraph()
                para.text = f"• {point}"
                para.font.size = Pt(22)
                para.font.color.rgb = colors["content_text"]
                para.space_before = Pt(12)
                para.space_after = Pt(6)

        if include_notes and outline.speaker_notes:
            slide.notes_slide.notes_text_frame.text = outline.speaker_notes

    def _add_section_slide(self, prs: Presentation, outline: SlideOutline, colors: dict):
        """Add a section divider slide."""
        if self._using_template:
            layout = self._find_layout(prs, SECTION_SLIDE_PATTERNS, LAYOUT_SECTION_HEADER)
            slide = prs.slides.add_slide(layout)

            for shape in slide.placeholders:
                if shape.placeholder_format.type in (1, 2):
                    shape.text = outline.title
                    break
            else:
                self._add_centered_title(slide, outline.title, Inches(3), Pt(40))
        else:
            self._add_title_slide_fallback(prs, outline, colors)

    def _add_closing_slide(self, prs: Presentation, outline: SlideOutline, colors: dict):
        """Add a closing/thank you slide."""
        if self._using_template:
            # Try to find closing layout, fall back to section or title
            layout = self._find_layout(prs, CLOSING_SLIDE_PATTERNS, LAYOUT_SECTION_HEADER)
            slide = prs.slides.add_slide(layout)

            for shape in slide.placeholders:
                if shape.placeholder_format.type in (1, 2):
                    shape.text = outline.title
                    break
            else:
                self._add_centered_title(slide, outline.title, Inches(3), Pt(40))
        else:
            self._add_title_slide_fallback(prs, outline, colors)

    def _add_centered_title(self, slide, text: str, top: Inches, font_size: Pt):
        """Helper to add centered title text."""
        text_box = slide.shapes.add_textbox(Inches(0.5), top, Inches(9), Inches(1.5))
        para = text_box.text_frame.paragraphs[0]
        para.text = text
        para.font.size = font_size
        para.font.bold = True
        para.alignment = PP_ALIGN.CENTER

    def _add_bullet_content(self, slide, bullets: List[str], top: Inches):
        """Helper to add bullet point content."""
        content_box = slide.shapes.add_textbox(Inches(0.75), top, Inches(8.5), Inches(5))
        tf = content_box.text_frame
        tf.word_wrap = True

        for i, point in enumerate(bullets):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.text = f"• {point}"
            para.font.size = Pt(20)
            para.space_before = Pt(10)

    def get_thumbnail(self, pptx_bytes: bytes) -> Optional[bytes]:
        """
        Generate a thumbnail of the first slide.

        Note: This is a placeholder - proper thumbnail generation
        requires additional libraries like pdf2image or libreoffice.
        """
        # For now, return None - thumbnail generation can be added later
        return None

    def get_available_templates(self) -> List[Dict[str, Any]]:
        """
        List all available template files.

        Returns:
            List of template info dicts with name, path, has_file, layout_count
        """
        templates = []

        # Built-in template names (always available as fallback)
        builtin_names = list(TEMPLATE_COLORS.keys())

        # Check for actual .pptx files
        available_files = set()
        if os.path.exists(self.templates_dir):
            for filename in os.listdir(self.templates_dir):
                if filename.endswith('.pptx'):
                    name = filename[:-5]  # Remove .pptx
                    available_files.add(name)

                    # Get layout count
                    try:
                        prs = Presentation(os.path.join(self.templates_dir, filename))
                        layout_count = len(prs.slide_layouts)
                    except Exception:
                        layout_count = 0

                    templates.append({
                        "name": name,
                        "has_file": True,
                        "layout_count": layout_count,
                        "file_path": os.path.join(self.templates_dir, filename),
                    })

        # Add built-in templates without files
        for name in builtin_names:
            if name not in available_files:
                templates.append({
                    "name": name,
                    "has_file": False,
                    "layout_count": 0,
                    "colors": {k: f"#{v.red:02x}{v.green:02x}{v.blue:02x}" for k, v in TEMPLATE_COLORS[name].items()},
                })

        return templates


def get_pptx_builder() -> PPTXBuilder:
    """Factory function to get PPTXBuilder instance."""
    return PPTXBuilder()
