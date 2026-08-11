import { describe, expect, it } from 'vitest'
import { trapFocus } from './focusTrap'

function pressTab(container: HTMLElement, shiftKey = false) {
  const event = new KeyboardEvent('keydown', { key: 'Tab', shiftKey, bubbles: true, cancelable: true })
  trapFocus(container, event)
  return event
}

describe('trapFocus', () => {
  it('Tab 从末项循环到首项', () => {
    const container = document.createElement('div')
    container.innerHTML = '<button id="first">首项</button><button id="last">末项</button>'
    document.body.append(container)
    const first = container.querySelector<HTMLElement>('#first')!
    const last = container.querySelector<HTMLElement>('#last')!
    last.focus()
    const event = pressTab(container)
    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)
    container.remove()
  })

  it('Shift+Tab 从首项循环到末项', () => {
    const container = document.createElement('div')
    container.innerHTML = '<button id="first">首项</button><button id="last">末项</button>'
    document.body.append(container)
    const first = container.querySelector<HTMLElement>('#first')!
    const last = container.querySelector<HTMLElement>('#last')!
    first.focus()
    const event = pressTab(container, true)
    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
    container.remove()
  })

  it('每次按键重新读取动态加入的可聚焦元素', () => {
    const container = document.createElement('div')
    container.innerHTML = '<button id="first">首项</button>'
    document.body.append(container)
    const first = container.querySelector<HTMLElement>('#first')!
    first.focus()
    const dynamic = document.createElement('button')
    container.append(dynamic)
    pressTab(container, true)
    expect(document.activeElement).toBe(dynamic)
    container.remove()
  })

  it('空容器阻止焦点逃逸并聚焦容器', () => {
    const container = document.createElement('div')
    container.tabIndex = -1
    document.body.append(container)
    const event = pressTab(container)
    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(container)
    container.remove()
  })

  it('焦点在容器外时 Tab 将焦点带回首项', () => {
    const outside = document.createElement('button')
    const container = document.createElement('div')
    container.innerHTML = '<button id="first">首项</button><button>末项</button>'
    document.body.append(outside, container)
    outside.focus()
    const event = pressTab(container)
    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(container.querySelector('#first'))
    outside.remove()
    container.remove()
  })
})
