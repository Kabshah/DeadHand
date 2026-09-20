import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { getSwitches } from '../api/switches';
import SwitchCard from '../components/SwitchCard';
import CreateSwitchModal from '../components/CreateSwitchModal';
import CheckinModal from '../components/CheckinModal';
import CancelModal from '../components/CancelModal';
import SwitchDetailModal from '../components/SwitchDetailModal';
import SystemStatusModal from '../components/SystemStatusModal';
import {
  Plus,
  RefreshCw,
  Shield,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Inbox,
  Search,
  LayoutGrid,
  List,
  Activity,
  LogOut,
  ChevronRight,
  Radio,
  FileText,
  Lock,
  ExternalLink,
  X,
} from 'lucide-react';

const MAX_SWITCHES_LIMIT = 5;

export default function DashboardPage() {
  const { user, logout, logoutUser } = useAuth();
  const toast = useToast();

  const handleLogout = useCallback(() => {
    if (typeof logout === 'function') {
      logout();
    } else if (typeof logoutUser === 'function') {
      logoutUser();
    } else {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/';
    }
  }, [logout, logoutUser]);

  const [switches, setSwitches] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState('all'); // all | active | triggered | cancelled
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState('grid'); // grid | table

  // Modal States
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [checkinTarget, setCheckinTarget] = useState(null);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [detailTarget, setDetailTarget] = useState(null);
  const [isSystemStatusOpen, setIsSystemStatusOpen] = useState(false);

  const fetchSwitches = useCallback(async (isSilent = false) => {
    if (!isSilent) setIsRefreshing(true);
    try {
      const data = await getSwitches();
      setSwitches(data?.switches || []);
    } catch (err) {
      toast.error(err.message || 'Failed to fetch switches.');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchSwitches();
    const interval = setInterval(() => fetchSwitches(true), 30000);
    return () => clearInterval(interval);
  }, [fetchSwitches]);

  // Derived metrics
  const activeSwitches = useMemo(() => switches.filter((s) => s.status === 'active'), [switches]);
  const triggeredSwitches = useMemo(() => switches.filter((s) => s.status === 'triggered'), [switches]);
  const cancelledSwitches = useMemo(() => switches.filter((s) => s.status === 'cancelled'), [switches]);

  const nearestActiveSwitch = useMemo(() => {
    if (!activeSwitches.length) return null;
    return [...activeSwitches].sort((a, b) => new Date(a.next_deadline) - new Date(b.next_deadline))[0];
  }, [activeSwitches]);

  const handleOpenCreate = useCallback(() => {
    if (activeSwitches.length >= MAX_SWITCHES_LIMIT) {
      toast.warning(`Active switch quota reached (${MAX_SWITCHES_LIMIT} max). Cancel or let an active switch expire before creating a new one.`);
      return;
    }
    setIsCreateOpen(true);
  }, [activeSwitches.length, toast]);

  // Filtered & searched list
  const filteredSwitches = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();

    // If searching, search across all switches so users don't get trapped in an empty status tab
    let pool = switches;
    if (!q) {
      if (activeTab === 'active') pool = activeSwitches;
      else if (activeTab === 'triggered') pool = triggeredSwitches;
      else if (activeTab === 'cancelled') pool = cancelledSwitches;
      return pool;
    }

    // Comprehensive multi-field search (case-insensitive substring match):
    return pool.filter((s) => {
      const idStr = String(s.id);
      const paddedId = `#dh-${idStr.padStart(4, '0')}`.toLowerCase();
      const legacyId = `#dms-${idStr.padStart(4, '0')}`.toLowerCase();
      const email = (s.recipient_email || '').toLowerCase();
      const status = (s.status || '').toLowerCase();
      const interval = String(s.interval_hours || '');

      return (
        email.includes(q) ||
        idStr.includes(q) ||
        paddedId.includes(q) ||
        legacyId.includes(q) ||
        status.includes(q) ||
        interval.includes(q)
      );
    });
  }, [activeTab, switches, activeSwitches, triggeredSwitches, cancelledSwitches, searchQuery]);

  const userInitial = user?.email ? user.email.charAt(0).toUpperCase() : 'U';

  const formatInterval = (hours) => {
    if (hours < 1) return `${Math.round(hours * 60)} Mins`;
    if (hours >= 24 && hours % 24 === 0) {
      const d = hours / 24;
      return `${d} ${d === 1 ? 'Day' : 'Days'}`;
    }
    return `${hours} Hrs`;
  };

  return (
    <div className="app-shell">
      {/* ── Top Unified Header & Navigation Bar ── */}
      <header className="main-header">
        <div className="header-left">
          {/* Brand Logo & Title */}
          <div className="nav-brand">
            <div className="brand-icon-wrapper">
              <Shield size={18} />
            </div>
            <div className="brand-text">
              <span className="brand-title">Dead Hand</span>
              <span className="brand-subtitle">Enterprise Safe</span>
            </div>
          </div>

          <div className="header-divider-v" />

          {/* System Status Quick Trigger */}
          <button
            type="button"
            className="status-pill-button"
            onClick={() => setIsSystemStatusOpen(true)}
            title="View system status and background workers"
          >
            <span className="status-dot-pulse" />
            <span>System Health</span>
            <Activity size={13} style={{ marginLeft: 2 }} />
          </button>
        </div>

        <div className="header-right">
          {/* Global Search Input */}
          <div className="search-input-wrapper">
            <Search size={14} className="search-input-icon" />
            <input
              type="text"
              placeholder="Search recipient, status, ID..."
              className="search-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button
                type="button"
                className="search-clear-btn"
                onClick={() => setSearchQuery('')}
                title="Clear search"
                aria-label="Clear search"
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* Account Capacity Metric Widget */}
          <div
            className="header-capacity-badge"
            title={`${activeSwitches.length} of ${MAX_SWITCHES_LIMIT} active switch slots used (${MAX_SWITCHES_LIMIT - activeSwitches.length} slot(s) available)`}
          >
            <div className="capacity-badge-content">
              <span className="capacity-label">Capacity</span>
              <strong className="capacity-val">{activeSwitches.length} / {MAX_SWITCHES_LIMIT}</strong>
            </div>
            <div className="capacity-mini-track">
              <div
                className="capacity-mini-fill"
                style={{ width: `${(activeSwitches.length / MAX_SWITCHES_LIMIT) * 100}%` }}
              />
            </div>
          </div>

          {/* Create Switch Button */}
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleOpenCreate}
            title="Create a switch"
          >
            <Plus size={15} />
            <span>Create a switch</span>
          </button>

          <div className="header-divider-v" />

          {/* Logged in User Badge & Sign Out Button */}
          <div className="header-user-wrapper">
            <div className="header-user-avatar" title={user?.email}>
              {userInitial}
            </div>
            <span className="header-user-email" title={user?.email}>
              {user?.email || 'Authenticated User'}
            </span>
            <button
              type="button"
              className="header-logout-btn"
              onClick={handleLogout}
              title="Sign Out"
              aria-label="Sign Out"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </header>

      {/* ── Main Application Panel ── */}
      <div className="app-main">
        {/* Main Body */}
        <main className="main-body">
          {/* Header Intro with Refresh Button */}
          <div className="page-intro-row">
            <div>
              <h1>Dead Hands Overview</h1>
              <p>Monitor automated fail-safe deadlines, perform scheduled check-ins, and manage encrypted disclosures.</p>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => fetchSwitches(false)}
              disabled={isRefreshing}
              title="Refresh switch list"
            >
              <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
              <span>{isRefreshing ? 'Refreshing...' : 'Refresh'}</span>
            </button>
          </div>

          {/* Metrics Grid */}
          <div className="metrics-grid">
            <div
              className={`metric-card green ${activeTab === 'active' ? 'selected' : ''}`}
              onClick={() => setActiveTab(activeTab === 'active' ? 'all' : 'active')}
              style={{ cursor: 'pointer' }}
              title="Click to toggle Active switches filter"
            >
              <div className="metric-top">
                <span className="metric-label">Active Switches</span>
                <div className="metric-icon-box">
                  <Shield size={18} />
                </div>
              </div>
              <div className="metric-value">{activeSwitches.length}</div>
              <div className="metric-sub">
                {MAX_SWITCHES_LIMIT - activeSwitches.length} slot(s) available
              </div>
              <div className="quota-box-track" style={{ marginTop: 8 }}>
                <div
                  className="quota-box-fill"
                  style={{ width: `${(activeSwitches.length / MAX_SWITCHES_LIMIT) * 100}%` }}
                />
              </div>
            </div>

            <div className="metric-card amber">
              <div className="metric-top">
                <span className="metric-label">Nearest Deadline</span>
                <div className="metric-icon-box">
                  <Clock size={18} />
                </div>
              </div>
              <div className="metric-value" style={{ fontSize: nearestActiveSwitch ? '1.25rem' : '1.75rem' }}>
                {nearestActiveSwitch
                  ? new Date(nearestActiveSwitch.next_deadline).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                  : '— —'}
              </div>
              <div className="metric-sub">
                {nearestActiveSwitch
                  ? `#DMS-${String(nearestActiveSwitch.id).padStart(4, '0')} (${nearestActiveSwitch.recipient_email})`
                  : 'No impending triggers'}
              </div>
            </div>

            <div
              className={`metric-card red ${activeTab === 'triggered' ? 'selected' : ''}`}
              onClick={() => setActiveTab(activeTab === 'triggered' ? 'all' : 'triggered')}
              style={{ cursor: 'pointer' }}
              title="Click to toggle Disclosed / Triggered filter"
            >
              <div className="metric-top">
                <span className="metric-label">Triggered / Disclosed</span>
                <div className="metric-icon-box">
                  <AlertTriangle size={18} />
                </div>
              </div>
              <div className="metric-value">{triggeredSwitches.length}</div>
              <div className="metric-sub">Dispatched to recipients</div>
            </div>

            <div
              className={`metric-card slate ${activeTab === 'all' ? 'selected' : ''}`}
              onClick={() => setActiveTab('all')}
              style={{ cursor: 'pointer' }}
              title="Click to view all switches"
            >
              <div className="metric-top">
                <span className="metric-label">Total Registered</span>
                <div className="metric-icon-box">
                  <CheckCircle2 size={18} />
                </div>
              </div>
              <div className="metric-value">{switches.length}</div>
              <div className="metric-sub">Lifetime switches configured</div>
            </div>
          </div>

          {/* Filter & View Switcher Bar */}
          <div className="control-bar">
            <div className="filter-pills">
              <button
                className={`filter-pill ${activeTab === 'all' ? 'active' : ''}`}
                onClick={() => setActiveTab('all')}
              >
                <span>All Switches</span>
                <span className="filter-pill-count">{switches.length}</span>
              </button>

              <button
                className={`filter-pill ${activeTab === 'active' ? 'active' : ''}`}
                onClick={() => setActiveTab('active')}
              >
                <span>Active</span>
                <span className="filter-pill-count">{activeSwitches.length}</span>
              </button>

              <button
                className={`filter-pill ${activeTab === 'triggered' ? 'active' : ''}`}
                onClick={() => setActiveTab('triggered')}
              >
                <span>Triggered</span>
                <span className="filter-pill-count">{triggeredSwitches.length}</span>
              </button>

              <button
                className={`filter-pill ${activeTab === 'cancelled' ? 'active' : ''}`}
                onClick={() => setActiveTab('cancelled')}
              >
                <span>Cancelled</span>
                <span className="filter-pill-count">{cancelledSwitches.length}</span>
              </button>
            </div>

            {/* Grid / Table View Switcher */}
            <div className="view-switcher">
              <button
                className={`view-btn ${viewMode === 'grid' ? 'active' : ''}`}
                onClick={() => setViewMode('grid')}
                title="Card View"
              >
                <LayoutGrid size={15} />
              </button>
              <button
                className={`view-btn ${viewMode === 'table' ? 'active' : ''}`}
                onClick={() => setViewMode('table')}
                title="Table View"
              >
                <List size={15} />
              </button>
            </div>
          </div>

          {/* Switches List Display */}
          {searchQuery.trim() && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 16px',
              background: 'var(--bg-app)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              marginBottom: 16,
              fontSize: '0.84rem',
              color: 'var(--text-secondary)'
            }}>
              <span>
                Found <strong>{filteredSwitches.length}</strong> record{filteredSwitches.length !== 1 ? 's' : ''} matching "<strong>{searchQuery}</strong>"
              </span>
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  textDecoration: 'underline'
                }}
              >
                Clear Search
              </button>
            </div>
          )}

          {isLoading ? (
            <div style={{ textAlign: 'center', padding: '60px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
              <RefreshCw size={26} style={{ color: 'var(--text-muted)' }} className="animate-spin" />
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading switches...</p>
            </div>
          ) : filteredSwitches.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon-box">
                <Inbox size={26} />
              </div>
              <h3>No dead hands found</h3>
              <p>
                {searchQuery
                  ? `No dead hands match your search for "${searchQuery}".`
                  : activeTab === 'all'
                  ? 'No dead hands configured yet. Arm a dead hand to encrypt confidential secrets for automatic delivery.'
                  : `No dead hands in "${activeTab}" status.`}
              </p>
              {searchQuery ? (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setSearchQuery('')}
                  style={{ marginTop: 12 }}
                >
                  Clear search filter
                </button>
              ) : activeTab === 'all' && (
                <button
                  className="btn btn-primary"
                  onClick={handleOpenCreate}
                >
                  <Plus size={16} />
                  <span>Create a switch</span>
                </button>
              )}
            </div>
          ) : viewMode === 'grid' ? (
            <div className="switches-grid">
              {filteredSwitches.map((switchItem) => (
                <SwitchCard
                  key={switchItem.id}
                  switchItem={switchItem}
                  onCheckin={(item) => setCheckinTarget(item)}
                  onCancel={(item) => setCancelTarget(item)}
                  onViewDetails={(item) => setDetailTarget(item)}
                />
              ))}
            </div>
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Switch ID</th>
                    <th>Recipient</th>
                    <th>Interval</th>
                    <th>Next Deadline</th>
                    <th>Status</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSwitches.map((s) => (
                    <tr key={s.id}>
                      <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                        #DMS-{String(s.id).padStart(4, '0')}
                      </td>
                      <td style={{ fontWeight: 500 }}>{s.recipient_email}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                        {formatInterval(s.interval_hours)}
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>
                        {s.status === 'active'
                          ? new Date(s.next_deadline).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })
                          : '—'}
                      </td>
                      <td>
                        <span className={`status-badge status-${s.status}`}>
                          {s.status}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                          {s.status === 'active' && (
                            <button
                              className="btn btn-success btn-sm"
                              onClick={() => setCheckinTarget(s)}
                            >
                              Check In
                            </button>
                          )}
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => setDetailTarget(s)}
                          >
                            Details
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </main>
      </div>

      {/* ── Modals ── */}
      {isCreateOpen && (
        <CreateSwitchModal
          isOpen={isCreateOpen}
          onClose={() => setIsCreateOpen(false)}
          onSuccess={() => {
            setIsCreateOpen(false);
            fetchSwitches(false);
          }}
        />
      )}

      {checkinTarget && (
        <CheckinModal
          isOpen={Boolean(checkinTarget)}
          switchItem={checkinTarget}
          onClose={() => setCheckinTarget(null)}
          onSuccess={() => {
            setCheckinTarget(null);
            fetchSwitches(false);
          }}
        />
      )}

      {cancelTarget && (
        <CancelModal
          isOpen={Boolean(cancelTarget)}
          switchItem={cancelTarget}
          onClose={() => setCancelTarget(null)}
          onSuccess={() => {
            setCancelTarget(null);
            fetchSwitches(false);
          }}
        />
      )}

      {detailTarget && (
        <SwitchDetailModal
          isOpen={Boolean(detailTarget)}
          switchItem={detailTarget}
          onClose={() => setDetailTarget(null)}
        />
      )}

      {isSystemStatusOpen && (
        <SystemStatusModal
          isOpen={isSystemStatusOpen}
          onClose={() => setIsSystemStatusOpen(false)}
        />
      )}
    </div>
  );
}
