# Inline Document Preview Design

**Date:** 2026-03-22
**Status:** Approved
**Scope:** Frontend — EmmaChat inline source rendering + fullscreen viewer

## Problem

The current document preview uses an `ArtifactsPanel` (side panel, 300-60vw resizable) that steals horizontal space from the chat and breaks the conversation flow. Users must click a document card, which opens a side panel — disconnecting the source from the context where it was cited.

## Solution

Replace the document preview flow with two layers:

1. **Inline Source Cards** — render directly below the AI response inside the chat flow, within the message width constraints (`max-w-[85%] sm:max-w-[75%]` inside `max-w-4xl`). Each source type has its own inline viewer.
2. **Fullscreen Overlay** — clicking "Abrir PDF" / "Abrir imagen" opens a fullscreen overlay. A close button returns to the chat at the same scroll position.

The `ArtifactsPanel` remains for Verified Generation, Predictive Analysis, and Forge tabs — only the document preview tab is removed from it.

## Inline Source Card Types

### PDF
- Header: red `PDF` badge + filename + page number + "Abrir PDF" button
- Body: renders the cited page as an A4 page (aspect-ratio 1:1.414) using `react-pdf` via the existing `PDFViewer` component
- Gray background behind the white A4 page, with subtle shadow (paper-on-desk effect)
- Page number at bottom center

### Image (JPG, PNG, WEBP)
- Header: green `IMG` badge + filename + "Abrir imagen" button
- Body: renders the image inline, scaled to fit the card width
- Gray background with subtle border

### Text / DOCX
- Header: blue `DOC` badge + filename + page number + "Descargar" button
- Body: text excerpt in a styled blockquote with left colored border
- No inline document rendering (excerpt only)

### BOE Legislation
- Header: purple `BOE` badge + law name + article number + "Ver en BOE" button
- Body: legislation excerpt in a styled blockquote with purple left border
- "Ver en BOE" opens external BOE URL

### Source Type Detection
- PDF: `fileType` contains "pdf" or filename ends with `.pdf`
- Image: `fileType` contains "image" or filename ends with `.jpg/.png/.webp/.gif`
- BOE: `source_type === "public_knowledge"` or `source_type === "legislation"`
- Text/Other: everything else — show excerpt with download button

## Fullscreen Overlay

- Fixed overlay (`position: fixed; inset: 0; z-index: 50`) with dark background
- Top toolbar: file type badge + filename + page navigation + zoom + download + red "Cerrar" button
- Content: reuses existing `PDFViewer` for PDFs, native `<img>` for images
- Close returns to chat, restoring scroll position
- Keyboard: `Escape` closes the overlay

## Components

### New Components
1. **`InlineSourceCard`** — replaces `DocumentDisplay` in `MessageBubble`. Detects source type and renders the appropriate inline viewer. Accepts `DocumentInfo` and an `onOpenFullscreen` callback.
2. **`FullscreenDocumentViewer`** — fullscreen overlay triggered by the "Abrir" button. Reuses blob fetching logic from existing `DocumentPreviewTab`. Renders at viewport level (portal or placed in `EmmaChat`).

### Modified Components
- **`MessageBubble`** — replace `<DocumentDisplay>` with `<InlineSourceCard>` for each document in `metadata.documents`
- **`EmmaChat`** — add fullscreen viewer state (`fullscreenDoc: DocumentInfo | null`), remove `previewDoc` from artifact tabs flow
- **`useArtifactTabs`** — remove the "Vista Previa" (preview) tab. Keep Verified Gen, Predictive, and Forge tabs.

### Reused Components
- **`PDFViewer`** — existing react-pdf viewer, used both inline (A4 render) and in fullscreen
- **`DocumentPreviewTab`** — blob fetching logic extracted/reused by `FullscreenDocumentViewer`
- **`useDocumentService`** — existing service for `downloadDocument()` and `searchDocuments()`

## Data Flow

```
metadata.documents[] (from useMessageConverter)
  → MessageBubble
    → InlineSourceCard (per document)
      → detects type (PDF/IMG/DOC/BOE)
      → PDF: fetches blob, renders PDFViewer inline (A4, cited page)
      → IMG: fetches blob, renders <img> inline
      → DOC: shows excerpt text
      → BOE: shows excerpt text
      → "Abrir" button → sets fullscreenDoc in EmmaChat
        → FullscreenDocumentViewer (fixed overlay)
          → reuses PDFViewer / <img> at full viewport
          → "Cerrar" → sets fullscreenDoc = null
```

## Layout Constraints

- Source cards render within `EmmaMessageFlow` (max-w-[85%] sm:max-w-[75%])
- Inside the `max-w-4xl mx-auto` container of `EmmaRenderChat`
- A4 pages scaled to fit the available width (max-width constrained)
- Fullscreen overlay is viewport-level, not constrained by chat layout

## Performance Considerations

- PDF blob fetch is async — show loading skeleton inside the A4 frame
- Only fetch blobs for PDFs and images; DOC/BOE only show text excerpts
- Lazy load: only fetch when the source card enters the viewport (IntersectionObserver)
- Cleanup blob URLs on unmount to prevent memory leaks
- Limit inline PDF rendering to the cited page only (single page, not multi-page)
