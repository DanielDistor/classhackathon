import { describe, expect, it } from 'vitest'
import { cardText, flightsPhrase, fmt } from './format.js'
import { linear, niceTicks } from './charts/scale.js'

describe('format', () => {
  it('says how many flights are left', () => {
    expect(flightsPhrase(-3)).toBe('now')
    expect(flightsPhrase(0.4)).toBe('now')
    expect(flightsPhrase(1)).toBe('in 1 flight')
    expect(flightsPhrase(11.6)).toBe('in 12 flights')
  })
  it('turns the first reason into a sentence', () => {
    expect(cardText('vibration signalled; motor too')).toBe('Vibration signalled.')
  })
  it('formats numbers and blanks', () => {
    expect(fmt(1234.567, 1)).toBe('1,234.6')
    expect(fmt(null)).toBe('–')
  })
})

describe('chart scales', () => {
  it('maps a domain onto a range', () => {
    const s = linear([0, 10], [100, 200])
    expect(s(0)).toBe(100)
    expect(s(5)).toBe(150)
    expect(s(10)).toBe(200)
  })
  it('handles a flat domain without dividing by zero', () => {
    expect(linear([3, 3], [0, 10])(3)).toBe(5)
  })
  it('picks round tick values inside the domain', () => {
    expect(niceTicks(0, 300, 6)).toEqual([0, 50, 100, 150, 200, 250, 300])
    expect(niceTicks(2.1, 3.9, 4)).toEqual([2.5, 3, 3.5])
  })
})
