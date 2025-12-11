/**
 * Utility for calculating visual caret (cursor) position in text inputs
 * Uses the "mirror element" technique to measure text width
 */

interface CaretCoordinates {
  top: number
  left: number
}

// Style properties that affect text measurement
const MIRROR_STYLE_PROPERTIES = [
  'fontFamily',
  'fontSize',
  'fontWeight',
  'fontStyle',
  'letterSpacing',
  'textTransform',
  'wordSpacing',
  'textIndent',
  'whiteSpace',
  'wordWrap',
  'boxSizing',
  'paddingTop',
  'paddingRight',
  'paddingBottom',
  'paddingLeft',
  'borderTopWidth',
  'borderRightWidth',
  'borderBottomWidth',
  'borderLeftWidth',
  'lineHeight'
] as const

/**
 * Calculate the visual coordinates of a specific character position in an input or textarea
 *
 * @param element - The input or textarea element
 * @param position - Character position (0-indexed)
 * @returns Object with top and left coordinates relative to the viewport
 */
export function getCaretCoordinates(
  element: HTMLInputElement | HTMLTextAreaElement,
  position: number
): CaretCoordinates {
  const isTextarea = element.nodeName === 'TEXTAREA'

  // Create mirror element
  const mirror = document.createElement('div')
  const computedStyle = window.getComputedStyle(element)

  // Copy relevant styles
  MIRROR_STYLE_PROPERTIES.forEach(prop => {
    mirror.style[prop as any] = computedStyle.getPropertyValue(
      prop.replace(/([A-Z])/g, '-$1').toLowerCase()
    )
  })

  // Set mirror positioning and dimensions
  mirror.style.position = 'absolute'
  mirror.style.visibility = 'hidden'
  mirror.style.overflow = 'hidden'
  mirror.style.whiteSpace = isTextarea ? 'pre-wrap' : 'nowrap'
  mirror.style.width = `${element.offsetWidth}px`

  if (isTextarea) {
    mirror.style.height = `${element.offsetHeight}px`
  }

  // Get text content up to the cursor position
  const textBeforeCaret = element.value.substring(0, position)

  // Replace spaces with non-breaking spaces to preserve width
  mirror.textContent = textBeforeCaret.replace(/ /g, '\u00A0')

  // Add a span to mark the caret position
  const caretMarker = document.createElement('span')
  caretMarker.textContent = '\u200B' // Zero-width space
  mirror.appendChild(caretMarker)

  // Add mirror to DOM temporarily
  document.body.appendChild(mirror)

  // Get element and caret positions
  const elementRect = element.getBoundingClientRect()
  const caretRect = caretMarker.getBoundingClientRect()
  const mirrorRect = mirror.getBoundingClientRect()

  // Calculate coordinates relative to viewport
  // Account for scroll position in the element
  const scrollLeft = element.scrollLeft || 0
  const scrollTop = element.scrollTop || 0

  const coordinates: CaretCoordinates = {
    left: elementRect.left + (caretRect.left - mirrorRect.left) - scrollLeft,
    top: elementRect.top + (caretRect.top - mirrorRect.top) - scrollTop
  }

  // Clean up
  document.body.removeChild(mirror)

  return coordinates
}

/**
 * Calculate the coordinates for a specific character in an input element
 * This is useful for positioning dropdowns near the trigger character (like "@")
 *
 * @param element - The input or textarea element
 * @param charIndex - Index of the character to get position for
 * @returns Coordinates for positioning a dropdown below the character
 */
export function getCharacterCoordinates(
  element: HTMLInputElement | HTMLTextAreaElement,
  charIndex: number
): CaretCoordinates {
  // Get the coordinates at the character position
  const coords = getCaretCoordinates(element, charIndex)

  // Get element rect for height calculation
  const elementRect = element.getBoundingClientRect()
  const computedStyle = window.getComputedStyle(element)
  const lineHeight = parseInt(computedStyle.lineHeight) || parseInt(computedStyle.fontSize) * 1.2

  return {
    left: coords.left,
    // Position below the character (add line height)
    top: coords.top + lineHeight
  }
}
