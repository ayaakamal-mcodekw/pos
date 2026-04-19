# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Restaurant/hospitality ERP system with POS integration. Built on **Laravel 10.x** (PHP 8.1+), Blade + Vue.js (Vite), and MySQL. Supports Arabic (default, RTL) and English, timezone Africa/Cairo.

---

## Commands

### Backend
```bash
php artisan serve          # Start development server
php artisan migrate        # Run pending migrations
php artisan test           # Run full PHPUnit test suite
php artisan test --filter=TestName   # Run a single test
php artisan queue:work     # Process queued jobs
php artisan key:generate   # Generate app encryption key
```

### Frontend
```bash
npm run dev     # Start Vite dev server (hot reload)
npm run build   # Build production assets
```

### Python POS Testing Tool
```bash
streamlit run pos_app.py   # Launch POS order automation UI
```

### Testing (`phpunit.xml`)
- Suites: `Unit`, `Feature`
- Default DB: MySQL (SQLite option commented out)
- Coverage target: `/app` directory

---

## Architecture

### API Layer — Role-Based Controller Split

All API controllers live under `app/Http/Controllers/Api/` and are split by user role:

| Namespace | Role |
|---|---|
| `AdminAPIs/` | Admin authentication, roles, permissions |
| `CashierAPIs/` | POS operations, orders, invoices, balance |
| `ClientAPIs/` | Client auth, orders, addresses, home |
| `KitchenAPIs/` | Kitchen order management |
| `WaiterAPIs/` | Table/invoice management |
| `DeliveryAPIs/` | Delivery routes, complaints |
| `CustomerServiceAPIs/` | Complaints, chats |

There are **13 route files** (`routes/`) split by domain: `api.php`, `dashboard.php`, `finance.php`, `hr.php`, `inventory.php`, `procurement.php`, `settings.php`, `website.php`, and others. `api_old.php` contains legacy endpoints — prefer the current `api.php`.

### Service / Repository Pattern

Business logic is separated into `app/Services/` (domain logic) and `app/Repositories/` (data access). Controllers should call Services, not query Eloquent directly. DTOs are used in `Modules/OrderManagement/DTOs/`.

### Modules

`/Modules/OrderManagement/` is a self-contained Laravel module with its own DTOs, Services, Controllers, and Routes. New feature modules may follow this pattern.

### Authentication

Multiple guards are configured: `web`, `api`, `admin`, `cashier`, `client`, `employee`, `delivery`. APIs authenticate via **Laravel Passport** (OAuth2) with Bearer tokens. Sanctum is also available for token-based auth. Role/permission enforcement is via **Spatie Permission**.

### Caching & Performance

- Redis/Memcached caching with 1-hour TTL on expensive queries (e.g. Menu API V2 achieves 15ms cached vs 600ms uncached).
- **Model Observers** (`app/Observers/`) auto-invalidate cache on model changes — always account for this when modifying models.
- Use eager loading; the Menu API refactor reduced queries from 50+ to 6–8 by fixing N+1 issues.

### Queue Jobs

14+ jobs in `app/Jobs/` handle async work: notifications, payroll generation, coupon management, invoice checks, reservation auto-cancellations. Jobs are dispatched from Services — do not dispatch directly from Controllers.

### Localization

Translation files in `resources/lang/ar/` and `resources/lang/en/`. Locale is set per-request via middleware. Default locale is `ar`. Always add both Arabic and English keys when adding user-facing strings.

### Key Integrations

- **MyFatoorah** — payment gateway (`config/myfatoorah.php`)
- **Firebase** — push notifications (`firebase-credentials.json`)
- **Pusher + Laravel Echo** — real-time broadcasting (`config/broadcasting.php`)
- **DomPDF** — PDF generation
- **Maatwebsite Excel** — export/import (`config/excel.php`)
- **Spatie ActivityLog** — all model changes are logged; models use the `LogsActivity` trait
- **Intervention Image / Spatie Image** — image processing

### Database

MySQL, strict mode **disabled** (`'strict' => false` in `config/database.php`). Models use `utf8mb4_unicode_ci`. Orders use UUIDs (`Str::uuid()`). Most models implement `SoftDeletes`. There are 362+ Eloquent models — check existing models before creating new ones.
