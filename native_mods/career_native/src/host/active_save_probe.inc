/* Active-save bridge. It observes FIFA's successful file I/O, publishes the
 * DATA path to the mod runtime folder, and notifies the optional background
 * retirement worker after a successful save write. */
typedef struct SaveReadHandle {
    HANDLE handle;
    char path[1024];
    BOOL recorded;
    unsigned char header[160];
    unsigned char seen[160];
    ULONGLONG read_end, write_end;
} SaveReadHandle;

#define SAVE_READ_HANDLE_CAPACITY 64
static SaveReadHandle g_save_read_handles[SAVE_READ_HANDLE_CAPACITY];
static SRWLOCK g_save_read_handles_lock = SRWLOCK_INIT;

static BOOL is_fifa_save_data_path(const char *path)
{
    const char *cursor = path;
    const char *last = NULL;
    const char *slot_end;
    size_t slot_length;
    if (!path || !*path)
        return FALSE;
    while (*cursor) {
        if (_strnicmp(cursor, "\\FIFA16\\", 8) == 0)
            last = cursor + 8;
        ++cursor;
    }
    if (!last)
        return FALSE;
    slot_end = strchr(last, '\\');
    if (!slot_end)
        return FALSE;
    slot_length = (size_t)(slot_end - last);
    if (slot_length == 0 || slot_length > 8
        || strlen(slot_end + 1) != 4 || _stricmp(slot_end + 1, "DATA") != 0)
        return FALSE;
    for (cursor = last; cursor < slot_end; ++cursor)
        if (!((*cursor >= '0' && *cursor <= '9')
            || (*cursor >= 'a' && *cursor <= 'f')
            || (*cursor >= 'A' && *cursor <= 'F')))
            return FALSE;
    return TRUE;
}

static BOOL get_save_data_path(HANDLE handle, char *path, size_t capacity)
{
    wchar_t wide_path[2048];
    DWORD length;
    int converted;
    if (path && capacity)
        path[0] = '\0';
    if (!g_get_final_path_name_by_handle_w || !path || capacity == 0)
        return FALSE;
    length = g_get_final_path_name_by_handle_w(handle, wide_path,
        (DWORD)(sizeof(wide_path) / sizeof(wide_path[0])), 0);
    if (length == 0 || length >= sizeof(wide_path) / sizeof(wide_path[0]))
        return FALSE;
    converted = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide_path,
        -1, path, (int)capacity, NULL, NULL);
    if (converted <= 0 || !is_fifa_save_data_path(path)) {
        path[0] = '\0';
        return FALSE;
    }
    return TRUE;
}

static void track_save_data_handle(HANDLE handle)
{
    char path[1024] = "";
    SIZE_T index;
    SIZE_T target = SAVE_READ_HANDLE_CAPACITY;
    if (handle == NULL || handle == INVALID_HANDLE_VALUE)
        return;
    (void)get_save_data_path(handle, path, sizeof(path));
    AcquireSRWLockExclusive(&g_save_read_handles_lock);
    for (index = 0; index < SAVE_READ_HANDLE_CAPACITY; ++index) {
        if (g_save_read_handles[index].handle == handle) {
            target = index;
            break;
        }
        if (target == SAVE_READ_HANDLE_CAPACITY
            && g_save_read_handles[index].handle == NULL)
            target = index;
    }
    if (target == SAVE_READ_HANDLE_CAPACITY)
        target = (SIZE_T)(GetTickCount64() % SAVE_READ_HANDLE_CAPACITY);
    memset(&g_save_read_handles[target], 0, sizeof(g_save_read_handles[target]));
    g_save_read_handles[target].handle = path[0] ? handle : NULL;
    g_save_read_handles[target].recorded = FALSE;
    lstrcpynA(g_save_read_handles[target].path, path,
              (int)sizeof(g_save_read_handles[target].path));
    ReleaseSRWLockExclusive(&g_save_read_handles_lock);
}

/* List previews read the container header too. Only a complete, contiguous
 * DATA payload with the Career type identifies the career FIFA loaded.
 * ReadFile/WriteFile buffers are observed after success; FIFA's buffer and
 * file position are never changed. Settings saves cannot replace this bridge. */
static BOOL observe_career_save_io(HANDLE handle, const void *buffer, DWORD amount,
    LPOVERLAPPED overlapped, BOOL writing, char *path, size_t capacity,
    ULONGLONG *file_size)
{
    LARGE_INTEGER size, position, zero;
    ULONGLONG offset, end;
    SIZE_T index;
    BOOL ready = FALSE;
    BOOL tracked = FALSE;
    char current_path[1024];
    if (!buffer || !amount || !path || !capacity || !file_size) return FALSE;
    /* Resource streaming also uses ReadFile. Do no filesystem work for an
     * untracked handle; revalidate only the small set of FIFA save handles. */
    AcquireSRWLockShared(&g_save_read_handles_lock);
    for(index=0;index<SAVE_READ_HANDLE_CAPACITY;++index)
        if(g_save_read_handles[index].handle==handle) {tracked=TRUE;break;}
    ReleaseSRWLockShared(&g_save_read_handles_lock);
    if (!tracked
        || !get_save_data_path(handle,current_path,sizeof(current_path))
        || !GetFileSizeEx(handle,&size) || size.QuadPart<0) return FALSE;
    if (overlapped) {
        offset=((ULONGLONG)overlapped->OffsetHigh<<32)|overlapped->Offset;
    } else {
        zero.QuadPart=0;
        if(!SetFilePointerEx(handle,zero,&position,FILE_CURRENT)
            || position.QuadPart<(LONGLONG)amount) return FALSE;
        offset=(ULONGLONG)position.QuadPart-amount;
    }
    if(offset>~(ULONGLONG)0-amount) return FALSE;
    end=offset+amount;
    AcquireSRWLockExclusive(&g_save_read_handles_lock);
    for(index=0;index<SAVE_READ_HANDLE_CAPACITY;++index) {
        SaveReadHandle *entry=&g_save_read_handles[index];
        ULONGLONG *covered;
        SIZE_T first,last,i;
        if(entry->handle!=handle || _stricmp(entry->path,current_path))continue;
        if(offset==0) {
            memset(entry->header,0,sizeof(entry->header));
            memset(entry->seen,0,sizeof(entry->seen));
            entry->read_end=entry->write_end=0;
            entry->recorded=FALSE;
        }
        first=offset<160?(SIZE_T)offset:160;
        last=end<160?(SIZE_T)end:160;
        for(i=first;i<last;++i) {
            entry->header[i]=((const unsigned char *)buffer)[i-(SIZE_T)offset];
            entry->seen[i]=1;
        }
        covered=writing?&entry->write_end:&entry->read_end;
        if(!writing && *covered==0 && offset==116)*covered=116;
        if(offset<=*covered && end>*covered)*covered=end;
        /* FIFA may read its outer header on a separate handle and then seek
         * this handle straight to the 116-byte payload boundary. Observing
         * that entire Career payload is sufficient; a title/list preview is
         * still far too small to satisfy this condition. */
        if(!entry->recorded && size.QuadPart>=220
            && (*covered>=(ULONGLONG)size.QuadPart
                || (!writing && offset<=116 && end>=(ULONGLONG)size.QuadPart
                    && amount>=(ULONGLONG)size.QuadPart-116))) {
            DWORD format=0,payload_size=0;
            for(i=116;i<140 && entry->seen[i];++i) {}
            memcpy(&format,entry->header+136,sizeof(format));
            memcpy(&payload_size,entry->header+100,sizeof(payload_size));
            if(i==140 && format==56
                /* Outer header says how much DATA follows its 116 bytes.
                 * A growing output file is not complete after its first chunk. */
                && (!writing || (entry->seen[100] && entry->seen[101]
                    && entry->seen[102] && entry->seen[103]
                    && (ULONGLONG)payload_size+116==(ULONGLONG)size.QuadPart))
                && !memcmp(entry->header+116,"SaveType_Career",16)) {
                lstrcpynA(path,current_path,(int)capacity);
                *file_size=(ULONGLONG)size.QuadPart;
                entry->recorded=TRUE;
                ready=TRUE;
            }
        }
        break;
    }
    ReleaseSRWLockExclusive(&g_save_read_handles_lock);
    return ready;
}

static BOOL write_career_save_bridge(const char *runtime_dir,
                                     const char *bridge_name,
                                     const char *temporary_name,
                                     const char *record, int length)
{
    char bridge_path[MAX_PATH], temporary_path[MAX_PATH];
    HANDLE file;
    DWORD written = 0;
    snprintf(bridge_path, sizeof(bridge_path), "%s\\%s", runtime_dir,
             bridge_name);
    snprintf(temporary_path, sizeof(temporary_path), "%s\\%s.%lu.%lu.tmp",
             runtime_dir, temporary_name, (unsigned long)GetCurrentProcessId(),
             (unsigned long)GetCurrentThreadId());
    file = CreateFileA(temporary_path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                       FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    if (WriteFile(file, record, (DWORD)length, &written, NULL) &&
        written == (DWORD)length) {
        FlushFileBuffers(file);
        CloseHandle(file);
        if (MoveFileExA(temporary_path, bridge_path,
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) return TRUE;
    } else {
        CloseHandle(file);
    }
    DeleteFileA(temporary_path);
    return FALSE;
}

static void publish_active_save_access(const char *path, const char *operation,
                                       DWORD bytes_transferred, ULONGLONG file_size)
{
    char runtime_dir[MAX_PATH];
    char record[1600];
    FILETIME created, exited, kernel, user;
    ULARGE_INTEGER created_value;
    int length;
    if (!is_fifa_save_data_path(path) || !operation ||
        bytes_transferred == 0 || !g_mod_dir[0]) return;
    if (!GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user))
        return;
    created_value.LowPart = created.dwLowDateTime;
    created_value.HighPart = created.dwHighDateTime;
    snprintf(runtime_dir, sizeof(runtime_dir), "%s\\runtime", g_mod_dir);
    if (!CreateDirectoryA(runtime_dir, NULL) &&
        GetLastError() != ERROR_ALREADY_EXISTS) return;
    length = snprintf(record, sizeof(record),
        "schema=3\r\npid=%lu\r\nprocess_created_100ns=%llu\r\n"
        "access_tick_ms=%llu\r\noperation=%s\r\nio_bytes=%lu\r\n"
        "save_type=SaveType_Career\r\ncomplete_file=1\r\nsize_bytes=%llu\r\npath=%s\r\n",
        (unsigned long)GetCurrentProcessId(),
        (unsigned long long)created_value.QuadPart,
        (unsigned long long)GetTickCount64(), operation,
        (unsigned long)bytes_transferred, (unsigned long long)file_size, path);
    if (length <= 0 || (size_t)length >= sizeof(record)) return;
    /* Keep the established bridge for existing mod tools and publish a
     * dedicated source bridge that cannot be confused with unrelated assets. */
    (void)write_career_save_bridge(runtime_dir, "career_active_save.tsv",
        "career_active_save", record, length);
    (void)write_career_save_bridge(runtime_dir, "career_save_source.tsv",
        "career_save_source", record, length);
}

static void record_career_ui_open(const char *path, HANDLE handle, DWORD error)
{
    const char *leaf;
    const char *cursor;
    char event[1400];
    if (!path)
        return;
    leaf = path;
    for (cursor = path; *cursor; ++cursor)
        if (*cursor == '\\' || *cursor == '/') leaf = cursor + 1;
    if (_stricmp(leaf, "careermanagerhubcfg.xml") != 0
        && _stricmp(leaf, "careerhubwidget.big") != 0
        && _stricmp(leaf, "mainmenuhubflow.nav") != 0)
        return;
    snprintf(event, sizeof(event), "career_ui_open success=%d error=%lu path=%s",
        handle != INVALID_HANDLE_VALUE, (unsigned long)error, path);
    append_loader_log(event);
}

static HANDLE WINAPI create_file_a_capture(
    LPCSTR name, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES security,
    DWORD creation, DWORD flags, HANDLE template_file)
{
    HANDLE handle;
    DWORD error;
    if (!g_original_create_file_a)
        return INVALID_HANDLE_VALUE;
    handle = g_original_create_file_a(name, access, share, security, creation,
                                      flags, template_file);
    error = GetLastError();
    record_career_ui_open(name, handle, error);
    if (handle != INVALID_HANDLE_VALUE)
        retirement_engine_note_ui_signal(name);
    track_save_data_handle(handle);
    SetLastError(error);
    return handle;
}

static HANDLE WINAPI create_file_w_capture(
    LPCWSTR name, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES security,
    DWORD creation, DWORD flags, HANDLE template_file)
{
    HANDLE handle;
    DWORD error;
    if (!g_original_create_file_w)
        return INVALID_HANDLE_VALUE;
    handle = g_original_create_file_w(name, access, share, security, creation,
                                      flags, template_file);
    error = GetLastError();
    if (name) {
        char signal_path[1024];
        if (WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, name, -1,
                signal_path, (int)sizeof(signal_path), NULL, NULL) > 0) {
            record_career_ui_open(signal_path, handle, error);
            if (handle != INVALID_HANDLE_VALUE)
                retirement_engine_note_ui_signal(signal_path);
        }
    }
    track_save_data_handle(handle);
    SetLastError(error);
    return handle;
}

static BOOL WINAPI read_file_capture(HANDLE handle, LPVOID buffer, DWORD length,
                                     LPDWORD bytes_read, LPOVERLAPPED overlapped)
{
    BOOL result;
    DWORD error;
    char path[1024];
    ULONGLONG file_size;
    if (!g_original_read_file)
        return FALSE;
    result = g_original_read_file(handle, buffer, length, bytes_read, overlapped);
    error = GetLastError();
    if (result && bytes_read && *bytes_read > 0
        && observe_career_save_io(handle, buffer, *bytes_read, overlapped, FALSE,
            path, sizeof(path), &file_size))
        publish_active_save_access(path, "read", *bytes_read, file_size);
    SetLastError(error);
    return result;
}

static BOOL WINAPI write_file_capture(HANDLE handle, LPCVOID buffer, DWORD length,
                                      LPDWORD bytes_written, LPOVERLAPPED overlapped)
{
    BOOL result;
    char path[1024];
    DWORD amount;
    DWORD error;
    ULONGLONG file_size;
    if (!g_original_write_file)
        return FALSE;
    result = g_original_write_file(handle, buffer, length, bytes_written,
        overlapped);
    error = GetLastError();
    amount = bytes_written ? *bytes_written : length;
    if (result && amount > 0 && observe_career_save_io(handle,buffer,amount,
            overlapped,TRUE,path,sizeof(path),&file_size)) {
        publish_active_save_access(path,"write",amount,file_size);
        retirement_engine_note_write(path);
    }
    SetLastError(error);
    return result;
}

static BOOL replace_import_address(HMODULE image, const char *function_name,
                                   void *replacement, void **original)
{
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)image;
    PIMAGE_NT_HEADERS nt;
    IMAGE_DATA_DIRECTORY directory;
    PIMAGE_IMPORT_DESCRIPTOR imports;
    DWORD index;
    if (!image || !function_name || !replacement || !original
        || dos->e_magic != IMAGE_DOS_SIGNATURE)
        return FALSE;
    nt = (PIMAGE_NT_HEADERS)((unsigned char *)image + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE)
        return FALSE;
    directory = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!directory.VirtualAddress || !directory.Size)
        return FALSE;
    imports = (PIMAGE_IMPORT_DESCRIPTOR)((unsigned char *)image
                                         + directory.VirtualAddress);
    for (index = 0; imports[index].Name; ++index) {
        PIMAGE_THUNK_DATA names;
        PIMAGE_THUNK_DATA addresses;
        DWORD thunk_index;
        const char *module_name = (const char *)image + imports[index].Name;
        if (_stricmp(module_name, "KERNEL32.dll") != 0
            && _stricmp(module_name, "KERNELBASE.dll") != 0)
            continue;
        if (!imports[index].OriginalFirstThunk)
            continue;
        names = (PIMAGE_THUNK_DATA)((unsigned char *)image
                                    + imports[index].OriginalFirstThunk);
        addresses = (PIMAGE_THUNK_DATA)((unsigned char *)image
                                        + imports[index].FirstThunk);
        for (thunk_index = 0; names[thunk_index].u1.AddressOfData;
             ++thunk_index) {
            PIMAGE_IMPORT_BY_NAME imported;
            DWORD previous_protection;
            ULONG_PTR current;
            if (IMAGE_SNAP_BY_ORDINAL(names[thunk_index].u1.Ordinal))
                continue;
            imported = (PIMAGE_IMPORT_BY_NAME)((unsigned char *)image
                + names[thunk_index].u1.AddressOfData);
            if (strcmp((const char *)imported->Name, function_name) != 0)
                continue;
            current = addresses[thunk_index].u1.Function;
            if (!VirtualProtect(&addresses[thunk_index].u1.Function,
                                sizeof(addresses[thunk_index].u1.Function),
                                PAGE_READWRITE, &previous_protection))
                return FALSE;
            *original = (void *)(uintptr_t)current;
            InterlockedExchangePointer(
                (PVOID volatile *)&addresses[thunk_index].u1.Function,
                replacement);
            (void)VirtualProtect(&addresses[thunk_index].u1.Function,
                sizeof(addresses[thunk_index].u1.Function), previous_protection,
                &previous_protection);
            FlushInstructionCache(GetCurrentProcess(),
                &addresses[thunk_index].u1.Function,
                sizeof(addresses[thunk_index].u1.Function));
            return TRUE;
        }
    }
    /* The FIFA executable is protected/relocated during startup.  In some
     * builds the loader leaves a valid IAT pointer but no longer leaves the
     * import-name thunk in the in-memory image.  Fall back to locating the
     * system API pointer in writable image sections (normally .idata). */
    {
        HMODULE kernel32 = GetModuleHandleW(L"kernel32.dll");
        HMODULE kernelbase = GetModuleHandleW(L"kernelbase.dll");
        void *targets[2];
        SIZE_T target_count = 0;
        WORD section_index;
        PIMAGE_SECTION_HEADER sections;
        if (kernel32) {
            void *target = (void *)GetProcAddress(kernel32, function_name);
            if (target) targets[target_count++] = target;
        }
        if (kernelbase) {
            void *target = (void *)GetProcAddress(kernelbase, function_name);
            if (target && (target_count == 0 || targets[0] != target))
                targets[target_count++] = target;
        }
        if (target_count == 0) return FALSE;
        sections = IMAGE_FIRST_SECTION(nt);
        for (section_index = 0; section_index < nt->FileHeader.NumberOfSections;
             ++section_index) {
            PIMAGE_SECTION_HEADER section = &sections[section_index];
            SIZE_T section_size = section->Misc.VirtualSize;
            SIZE_T offset;
            unsigned char *start;
            if (!(section->Characteristics & IMAGE_SCN_MEM_WRITE))
                continue;
            if (section_size < sizeof(void *)) continue;
            if ((SIZE_T)section->VirtualAddress >= nt->OptionalHeader.SizeOfImage)
                continue;
            if ((SIZE_T)section->VirtualAddress + section_size
                > nt->OptionalHeader.SizeOfImage)
                section_size = nt->OptionalHeader.SizeOfImage
                    - (SIZE_T)section->VirtualAddress;
            start = (unsigned char *)image + section->VirtualAddress;
            for (offset = 0; offset + sizeof(void *) <= section_size;
                 offset += sizeof(void *)) {
                void **slot = (void **)(start + offset);
                void *current = *slot;
                SIZE_T target_index;
                for (target_index = 0; target_index < target_count;
                     ++target_index) {
                    DWORD previous_protection;
                    if (current != targets[target_index]) continue;
                    if (!VirtualProtect(slot, sizeof(*slot), PAGE_READWRITE,
                            &previous_protection))
                        return FALSE;
                    *original = current;
                    InterlockedExchangePointer((PVOID volatile *)slot,
                        replacement);
                    (void)VirtualProtect(slot, sizeof(*slot),
                        previous_protection, &previous_protection);
                    FlushInstructionCache(GetCurrentProcess(), slot,
                        sizeof(*slot));
                    append_loader_log("active_save_probe_pointer_scan_installed");
                    return TRUE;
                }
            }
        }
    }
    /* This mod targets the verified FIFA 16 executable build (SizeOfImage
     * 0x09525000). Its four save-related IAT slots are stable even when the
     * protected loader changes the import metadata. Validate the image size
     * before using these RVAs so a different executable cannot be patched by
     * accident. */
    if (g_module_size == 0x09525000U) {
        uintptr_t known_rva = 0;
        if (strcmp(function_name, "CreateFileA") == 0)
            known_rva = 0x05F682A8U;
        else if (strcmp(function_name, "ReadFile") == 0)
            known_rva = 0x05F682C8U;
        else if (strcmp(function_name, "CreateFileW") == 0)
            known_rva = 0x05F68328U;
        else if (strcmp(function_name, "WriteFile") == 0)
            known_rva = 0x05F68340U;
        if (known_rva) {
            void **slot = (void **)((unsigned char *)image + known_rva);
            void *current = *slot;
            DWORD previous_protection;
            if (current && current != replacement
                && VirtualProtect(slot, sizeof(*slot), PAGE_READWRITE,
                    &previous_protection)) {
                *original = current;
                InterlockedExchangePointer((PVOID volatile *)slot,
                    replacement);
                (void)VirtualProtect(slot, sizeof(*slot),
                    previous_protection, &previous_protection);
                FlushInstructionCache(GetCurrentProcess(), slot,
                    sizeof(*slot));
                append_loader_log("active_save_probe_known_iat_installed");
                return TRUE;
            }
        }
    }
    return FALSE;
}

static BOOL install_active_save_read_probe(HMODULE image)
{
    HMODULE kernel32 = GetModuleHandleW(L"kernel32.dll");
    g_get_final_path_name_by_handle_w = kernel32
        ? (GetFinalPathNameByHandleWFn)GetProcAddress(
            kernel32, "GetFinalPathNameByHandleW") : NULL;
    if (replace_import_address(image, "CreateFileA",
            (void *)create_file_a_capture, (void **)&g_original_create_file_a))
        InterlockedIncrement(&g_save_file_hook_count);
    else
        append_loader_log("active_save_probe_CreateFileA_not_found");
    if (replace_import_address(image, "CreateFileW",
            (void *)create_file_w_capture, (void **)&g_original_create_file_w))
        InterlockedIncrement(&g_save_file_hook_count);
    else
        append_loader_log("active_save_probe_CreateFileW_not_found");
    if (replace_import_address(image, "ReadFile",
            (void *)read_file_capture, (void **)&g_original_read_file))
        InterlockedIncrement(&g_save_file_hook_count);
    else
        append_loader_log("active_save_probe_ReadFile_not_found");
    if (replace_import_address(image, "WriteFile",
            (void *)write_file_capture, (void **)&g_original_write_file))
        InterlockedIncrement(&g_save_file_hook_count);
    else
        append_loader_log("active_save_probe_WriteFile_not_found");
    if (!g_original_create_file_a && !g_original_create_file_w)
        goto incomplete;
    append_loader_log("active_save_probe_iat_installed");
    return TRUE;

incomplete:
    append_loader_log("active_save_probe_iat_install_incomplete");
    return FALSE;
}
