# Presentation Templates

This directory contains PowerPoint template files (.pptx) used for generating presentations.

## How to Add Templates

1. **Download a template** from one of these sources:
   - **Microsoft Create** (https://create.microsoft.com) - Free, no attribution required
   - **SlidesCarnival** (https://slidescarnival.com) - CC-BY license, attribution optional for personal use
   - **PowerPointBase** - Free commercial use

2. **Name the file** to match a template ID:
   - `corporate.pptx`
   - `educational.pptx`
   - `minimal.pptx`
   - `creative.pptx`
   - `nouxcube.pptx`
   - `professional-blue.pptx`
   - `modern-gradient.pptx`
   - `tech-dark.pptx`
   - `nature-green.pptx`
   - `business-clean.pptx`
   - `startup-pitch.pptx`
   - `academic-formal.pptx`
   - `marketing-bold.pptx`
   - `finance-elegant.pptx`

3. **Place the file** in this directory (`/templates/`)

## Template Requirements

For best results, templates should have these slide layouts:
- **Title Slide** - For the presentation title (layout index 0)
- **Title and Content** - For bullet point slides (layout index 1)
- **Section Header** - For divider slides (layout index 2)

The builder automatically detects layouts by searching for:
- Title patterns: "title slide", "título", "portada", "cover"
- Content patterns: "title and content", "content", "bullets"
- Section patterns: "section", "sección", "header", "divider"

## Fallback Behavior

If no template file is found:
1. The builder first tries to use any available .pptx file as fallback
2. If no files exist, it creates slides programmatically using color schemes

## Color Schemes

Built-in templates without .pptx files use these color schemes:
- **Corporate**: Blue (#005A9C)
- **Educational**: Green (#2E7D32)
- **Minimal**: Light Gray (#F5F5F5)
- **Creative**: Purple (#7B1FA2)
- **NouxCube**: Dark Blue (#1E3A5F)

## Testing

To verify your template works correctly:
```bash
# Check available templates
curl http://localhost:8009/templates

# Generate a test presentation
curl -X POST http://localhost:8009/generate \
  -H "Content-Type: application/json" \
  -d '{"template": "your-template-name", ...}'
```
