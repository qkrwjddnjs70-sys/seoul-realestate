import React from 'react'
import ReactDOM from 'react-dom/client'
import axios from 'axios'
import App from './App'
import './index.css'

// ─── 관리자 우회 토큰 자동 처리 ─────────────────────────────
// 1) URL에 ?admin=토큰 있으면 localStorage 저장 후 URL 정리
// 2) 이후 모든 fetch/axios 요청에 X-Admin-Token 헤더 자동 추가
const params = new URLSearchParams(window.location.search)
const adminFromUrl = params.get('admin')
if (adminFromUrl) {
  localStorage.setItem('admin_token', adminFromUrl)
  params.delete('admin')
  const newSearch = params.toString()
  window.history.replaceState({}, '',
    window.location.pathname + (newSearch ? '?' + newSearch : '') + window.location.hash)
  console.log('[admin] 관리자 모드 활성 — 무제한')
}
// 관리자 해제: localStorage.removeItem('admin_token') 후 새로고침

const adminToken = localStorage.getItem('admin_token')
if (adminToken) {
  // axios 글로벌 헤더
  axios.defaults.headers.common['X-Admin-Token'] = adminToken
  // fetch 글로벌 래퍼
  const _origFetch = window.fetch
  window.fetch = (input, init = {}) => {
    init.headers = { ...(init.headers || {}), 'X-Admin-Token': adminToken }
    return _origFetch(input, init)
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
