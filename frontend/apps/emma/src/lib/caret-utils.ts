/**
 * Utility for calculating visual caret (cursor) position in text inputs
 * Uses the "mirror element" technique to measure text width
 */

interface CaretCoordinates {
  top: number
  left: number
}

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
 */
export function getCaretCoordinates(
  element: HTMLInputElement | HTMLTextAreaElement,
  position: number
): CaretCoordinates {
  const isTextarea = element.nodeName === 'TEXTAREA'

  const mirror = document.createElement('div')
  const computedStyle = window.getComputedStyle(element)

  MIRROR_STYLE_PROPERTIES.forEach(prop => {
    mirror.style[prop as keyof CSSStyleDeclaration] = computedStyle.getPropertyValue(
      prop.replace(/([A-Z])/g, '-$1').toLowerCase()
    ) as string
  })

  mirror.style.position = 'absolute'
  mirror.style.visibility = 'hidden'
  mirror.style.overflow = 'hidden'
  mirror.style.whiteSpace = isTextarea ? 'pre-wrap' : 'nowrap'
  mirror.style.width = `${element.offsetWidth}px`

  if (isTextarea) {
    mirror.style.height = `${element.offsetHeight}px`
  }

  const textBeforeCaret = element.value.substring(0, position)
  mirror.textContent = textBeforeCaret.replace(/ /g, '\u00A0')

  const caretMarker = document.createElement('span')
  caretMarker.textContent = '\u200B'
  mirror.appendChild(caretMarker)

  document.body.appendChild(mirror)

  const elementRect = element.getBoundingClientRect()
  const caretRect = caretMarker.getBoundingClientRect()
  const mirrorRect = mirror.getBoundingClientRect()

  const scrollLeft = element.scrollLeft || 0
  const scrollTop = element.scrollTop || 0

  const coordinates: CaretCoordinates = {
    left: elementRect.left + (caretRect.left - mirrorRect.left) - scrollLeft,
    top: elementRect.top + (caretRect.top - mirrorRect.top) - scrollTop
  }

  document.body.removeChild(mirror)

  return coordinates
}

/**
 * Calculate the coordinates for a specific character in an input element
 */
export function getCharacterCoordinates(
  element: HTMLInputElement | HTMLTextAreaElement,
  charIndex: number
): CaretCoordinates {
  const coords = getCaretCoordinates(element, charIndex)
  const computedStyle = window.getComputedStyle(element)
  const lineHeight = parseInt(computedStyle.lineHeight) || parseInt(computedStyle.fontSize) * 1.2

  return {
    left: coords.left,
    top: coords.top + lineHeight
  }
}
