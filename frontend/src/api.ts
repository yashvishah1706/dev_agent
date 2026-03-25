import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })

// Attach JWT to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Redirect to login on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

export const login = async (username: string, password: string) => {
  const form = new URLSearchParams()
  form.append('username', username)
  form.append('password', password)
  const res = await api.post('/auth/token', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return res.data
}

export const analyzeRepo = async (repoUrl: string, branch = 'main') =>
  api.post('/analyze', { repo_url: repoUrl, branch }).then((r) => r.data)

export const getJob = async (jobId: string) =>
  api.get(`/jobs/${jobId}`).then((r) => r.data)

export const listJobs = async () =>
  api.get('/jobs').then((r) => r.data)
