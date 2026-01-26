#!/usr/bin/env python3
"""
Create Presentation Templates with Proper Structure

Generates .pptx templates optimized for LLM-based content merging.
Each template has:
1. Title slide (position 0)
2. Content slide (position 1) - duplicated for additional slides
3. Clear text hierarchy for title/content detection

The PPTXBuilder duplicates slide 1 for each content slide needed,
then modifies the text content while preserving the visual design.

Usage:
    python scripts/create_demo_templates.py
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE


# Template definitions with color schemes
TEMPLATES = {
    "corporate": {
        "name": "Corporate Professional",
        "primary": RGBColor(0x00, 0x5A, 0x9C),    # Blue
        "secondary": RGBColor(0x00, 0x3D, 0x6B),  # Dark blue
        "accent": RGBColor(0x00, 0x96, 0xD6),     # Light blue
        "text_light": RGBColor(0xFF, 0xFF, 0xFF), # White
        "text_dark": RGBColor(0x33, 0x33, 0x33),  # Dark gray
        "background": RGBColor(0xFF, 0xFF, 0xFF), # White
    },
    "educational": {
        "name": "Educational Modern",
        "primary": RGBColor(0x2E, 0x7D, 0x32),    # Green
        "secondary": RGBColor(0x1B, 0x5E, 0x20),  # Dark green
        "accent": RGBColor(0x66, 0xBB, 0x6A),     # Light green
        "text_light": RGBColor(0xFF, 0xFF, 0xFF),
        "text_dark": RGBColor(0x33, 0x33, 0x33),
        "background": RGBColor(0xFF, 0xFF, 0xFF),
    },
    "minimal": {
        "name": "Minimal Clean",
        "primary": RGBColor(0x42, 0x42, 0x42),    # Dark gray
        "secondary": RGBColor(0x21, 0x21, 0x21),  # Black
        "accent": RGBColor(0x75, 0x75, 0x75),     # Medium gray
        "text_light": RGBColor(0xFF, 0xFF, 0xFF),
        "text_dark": RGBColor(0x21, 0x21, 0x21),
        "background": RGBColor(0xFA, 0xFA, 0xFA), # Off-white
    },
    "creative": {
        "name": "Creative Bold",
        "primary": RGBColor(0x7B, 0x1F, 0xA2),    # Purple
        "secondary": RGBColor(0x4A, 0x14, 0x8C),  # Dark purple
        "accent": RGBColor(0xE1, 0xBE, 0xE7),     # Light purple
        "text_light": RGBColor(0xFF, 0xFF, 0xFF),
        "text_dark": RGBColor(0x33, 0x33, 0x33),
        "background": RGBColor(0xFF, 0xFF, 0xFF),
    },
    "nouxcube": {
        "name": "NouxCube Brand",
        "primary": RGBColor(0x1E, 0x3A, 0x5F),    # Dark blue
        "secondary": RGBColor(0x0D, 0x23, 0x3D),  # Darker blue
        "accent": RGBColor(0x4A, 0x90, 0xD9),     # Light blue
        "text_light": RGBColor(0xFF, 0xFF, 0xFF),
        "text_dark": RGBColor(0x1E, 0x3A, 0x5F),
        "background": RGBColor(0xFF, 0xFF, 0xFF),
    },
}


def create_template(template_name: str, colors: dict, output_dir: str):
    """
    Create a .pptx template optimized for content merging.

    Structure:
    - Slide 0: Title slide (full background, centered title/subtitle)
    - Slide 1: Content slide (header bar + content area) - THIS IS DUPLICATED

    The PPTXBuilder will:
    1. Modify slide 0 with the presentation title
    2. Duplicate slide 1 for each content slide
    3. Modify text in each duplicated slide
    """
    prs = Presentation()
    prs.slide_width = Inches(13.333)  # 16:9 widescreen
    prs.slide_height = Inches(7.5)

    # Get blank layout
    slide_layout = prs.slide_layouts[6]  # Blank layout

    # ========================================
    # SLIDE 0: TITLE SLIDE
    # ========================================
    slide = prs.slides.add_slide(slide_layout)

    # Full-slide background
    bg_shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0),
        prs.slide_width, prs.slide_height
    )
    bg_shape.fill.solid()
    bg_shape.fill.fore_color.rgb = colors["primary"]
    bg_shape.line.fill.background()
    bg_shape.name = "Background"

    # Decorative accent bar at bottom
    accent_bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(6.5),
        prs.slide_width, Inches(1)
    )
    accent_bar.fill.solid()
    accent_bar.fill.fore_color.rgb = colors["secondary"]
    accent_bar.line.fill.background()
    accent_bar.name = "AccentBar"

    # TITLE text box - positioned at top-center
    # This will be detected by PPTXBuilder due to position (top < 2 inches from top)
    title_box = slide.shapes.add_textbox(
        Inches(0.75), Inches(2.5),
        Inches(11.8), Inches(1.5)
    )
    title_box.name = "Title"
    title_frame = title_box.text_frame
    title_frame.word_wrap = True
    title_para = title_frame.paragraphs[0]
    title_para.text = "[TITLE]"  # Placeholder text
    title_para.font.size = Pt(54)
    title_para.font.bold = True
    title_para.font.color.rgb = colors["text_light"]
    title_para.alignment = PP_ALIGN.CENTER

    # SUBTITLE text box - positioned below title
    subtitle_box = slide.shapes.add_textbox(
        Inches(0.75), Inches(4.2),
        Inches(11.8), Inches(1.2)
    )
    subtitle_box.name = "Subtitle"
    sub_frame = subtitle_box.text_frame
    sub_frame.word_wrap = True
    sub_para = sub_frame.paragraphs[0]
    sub_para.text = "[SUBTITLE]"
    sub_para.font.size = Pt(24)
    sub_para.font.color.rgb = colors["accent"]
    sub_para.alignment = PP_ALIGN.CENTER

    # ========================================
    # SLIDE 1: CONTENT SLIDE (Template for duplication)
    # ========================================
    slide = prs.slides.add_slide(slide_layout)

    # Header bar with primary color
    header = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0),
        prs.slide_width, Inches(1.3)
    )
    header.fill.solid()
    header.fill.fore_color.rgb = colors["primary"]
    header.line.fill.background()
    header.name = "HeaderBar"

    # TITLE text box - in the header bar (top position)
    title_box = slide.shapes.add_textbox(
        Inches(0.75), Inches(0.35),
        Inches(11.8), Inches(0.8)
    )
    title_box.name = "Title"
    title_frame = title_box.text_frame
    title_frame.word_wrap = True
    title_para = title_frame.paragraphs[0]
    title_para.text = "[SLIDE TITLE]"
    title_para.font.size = Pt(36)
    title_para.font.bold = True
    title_para.font.color.rgb = colors["text_light"]

    # CONTENT text box - main content area below header
    content_box = slide.shapes.add_textbox(
        Inches(0.75), Inches(1.8),
        Inches(11.8), Inches(5.2)
    )
    content_box.name = "Content"
    content_frame = content_box.text_frame
    content_frame.word_wrap = True

    # Add sample bullet points
    bullet_texts = ["[Point 1]", "[Point 2]", "[Point 3]"]
    for i, text in enumerate(bullet_texts):
        if i == 0:
            para = content_frame.paragraphs[0]
        else:
            para = content_frame.add_paragraph()
        para.text = text
        para.font.size = Pt(24)
        para.font.color.rgb = colors["text_dark"]
        para.space_before = Pt(12)
        para.space_after = Pt(6)

    # Footer accent line
    footer_line = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(7.3),
        prs.slide_width, Inches(0.2)
    )
    footer_line.fill.solid()
    footer_line.fill.fore_color.rgb = colors["accent"]
    footer_line.line.fill.background()
    footer_line.name = "FooterLine"

    # Save template
    output_path = os.path.join(output_dir, f"{template_name}.pptx")
    prs.save(output_path)

    # Verify structure
    verify_prs = Presentation(output_path)
    print(f"Created: {template_name}.pptx")
    print(f"  Slides: {len(verify_prs.slides)}")
    for i, s in enumerate(verify_prs.slides):
        shapes = len(s.shapes)
        text_shapes = sum(1 for sh in s.shapes if sh.has_text_frame)
        print(f"    Slide {i}: {shapes} shapes ({text_shapes} with text)")

    return output_path


def main():
    """Create all templates."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(script_dir, "..", "templates")
    os.makedirs(templates_dir, exist_ok=True)

    print(f"Creating templates in: {templates_dir}")
    print("=" * 60)

    for template_name, colors in TEMPLATES.items():
        try:
            create_template(template_name, colors, templates_dir)
            print()
        except Exception as e:
            print(f"Error creating {template_name}: {e}")
            import traceback
            traceback.print_exc()

    print("=" * 60)
    print(f"Created {len(TEMPLATES)} templates successfully!")
    print("\nStructure of each template:")
    print("  - Slide 0: Title slide (full background, title + subtitle)")
    print("  - Slide 1: Content slide (header + bullets) - THIS IS DUPLICATED")
    print("\nThe PPTXBuilder will:")
    print("  1. Modify slide 0 with presentation title")
    print("  2. Duplicate slide 1 for each content slide")
    print("  3. Replace [TITLE], [SLIDE TITLE], [Point X] with actual content")


if __name__ == "__main__":
    main()
