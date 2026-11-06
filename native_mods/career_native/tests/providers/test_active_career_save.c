/* Exercise the real successful-I/O observer without attaching to FIFA. */
#include "../../src/host/dinput8_wrapper.c"
#define CHECK(x) do {if(!(x)){printf("FAIL %d: %s error=%lu\n",__LINE__,#x,GetLastError());return 1;}}while(0)

static void fixture(const wchar_t *path,int career)
{
    unsigned char data[4096]={0};
    HANDLE file;
    DWORD amount,format=56,payload_size=sizeof(data)-116,crc=305419896;
    memcpy(data+116,career?"SaveType_Career":"SaveType_Settin",16);
    memcpy(data+136,&format,4);
    memcpy(data+100,&payload_size,4);
    memcpy(data+132,&crc,4);
    file=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,CREATE_ALWAYS,0,NULL);
    WriteFile(file,data,sizeof(data),&amount,NULL);CloseHandle(file);
}

static int bridge_has(const char *leaf)
{
    char file[MAX_PATH],text[1800]={0};
    FILE *stream;
    snprintf(file,sizeof(file),"%s\\runtime\\career_save_source.tsv",g_mod_dir);
    stream=fopen(file,"rb");if(!stream)return 0;
    fread(text,1,sizeof(text)-1,stream);fclose(stream);
    return strstr(text,"schema=3") && strstr(text,"complete_file=1")
        && strstr(text,"save_type=SaveType_Career") && strstr(text,leaf);
}

static int durable_receipts(void)
{
    char pattern[MAX_PATH],path[MAX_PATH],text[1800];WIN32_FIND_DATAA found;
    HANDLE search;int count=0;FILE *file;size_t size;
    snprintf(pattern,sizeof(pattern),"%s\\runtime\\manager_market\\save_events\\*.tsv",g_mod_dir);
    search=FindFirstFileA(pattern,&found);if(search==INVALID_HANDLE_VALUE)return 0;
    do {
        snprintf(path,sizeof(path),"%s\\runtime\\manager_market\\save_events\\%s",g_mod_dir,found.cFileName);
        file=fopen(path,"rb");if(!file){count=-100;break;}
        size=fread(text,1,sizeof(text)-1,file);text[size]=0;fclose(file);
        if(!strstr(text,"operation=write")||!strstr(text,"payload_crc32=305419896")
            ||!strstr(text,"context=1e")||!strstr(text,"epoch=2")){count=-100;break;}
        ++count;
    }while(FindNextFileA(search,&found));
    FindClose(search);return count;
}

int main(void)
{
    wchar_t temporary[MAX_PATH],root[MAX_PATH],folder[MAX_PATH],a[MAX_PATH],b[MAX_PATH],settings[MAX_PATH];
    unsigned char data[4096];
    DWORD amount;
    HANDLE handle;
    HMODULE kernel=GetModuleHandleW(L"kernel32.dll");
    GetTempPathW(MAX_PATH,temporary);
    swprintf(root,MAX_PATH,L"%lsff16_career_io_%lu_%llu",temporary,GetCurrentProcessId(),GetTickCount64());
    CreateDirectoryW(root,NULL);
    WideCharToMultiByte(CP_UTF8,0,root,-1,g_mod_dir,sizeof(g_mod_dir),NULL,NULL);
    swprintf(folder,MAX_PATH,L"%ls\\FIFA16",root);CreateDirectoryW(folder,NULL);
    swprintf(folder,MAX_PATH,L"%ls\\FIFA16\\aaa",root);CreateDirectoryW(folder,NULL);
    swprintf(a,MAX_PATH,L"%ls\\DATA",folder);fixture(a,1);
    swprintf(folder,MAX_PATH,L"%ls\\FIFA16\\bbb",root);CreateDirectoryW(folder,NULL);
    swprintf(b,MAX_PATH,L"%ls\\DATA",folder);fixture(b,1);
    swprintf(folder,MAX_PATH,L"%ls\\FIFA16\\ccc",root);CreateDirectoryW(folder,NULL);
    swprintf(settings,MAX_PATH,L"%ls\\DATA",folder);fixture(settings,0);
    g_original_create_file_w=(CreateFileWFn)GetProcAddress(kernel,"CreateFileW");
    g_original_read_file=(ReadFileFn)GetProcAddress(kernel,"ReadFile");
    g_original_write_file=(WriteFileFn)GetProcAddress(kernel,"WriteFile");
    g_get_final_path_name_by_handle_w=(GetFinalPathNameByHandleWFn)GetProcAddress(kernel,"GetFinalPathNameByHandleW");
    g_career_context_identity=(void *)(uintptr_t)30;Fifa16CareerContextRead.epoch=2;
    handle=create_file_w_capture(a,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(handle!=INVALID_HANDLE_VALUE);
    CHECK(read_file_capture(handle,data,116,&amount,NULL));
    CHECK(!bridge_has("aaa\\DATA"));
    CHECK(read_file_capture(handle,data,1000,&amount,NULL));
    CHECK(!bridge_has("aaa\\DATA"));
    CHECK(read_file_capture(handle,data,4096,&amount,NULL));
    CHECK(bridge_has("aaa\\DATA"));CloseHandle(handle);
    /* Full settings reads and save-list header previews cannot replace A. */
    handle=create_file_w_capture(settings,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(read_file_capture(handle,data,4096,&amount,NULL));CloseHandle(handle);
    CHECK(bridge_has("aaa\\DATA"));
    handle=create_file_w_capture(b,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(read_file_capture(handle,data,160,&amount,NULL));CloseHandle(handle);
    CHECK(bridge_has("aaa\\DATA"));
    /* A later full career load replaces A even if its disk mtime is older. */
    handle=create_file_w_capture(b,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(read_file_capture(handle,data,4096,&amount,NULL));CloseHandle(handle);
    CHECK(bridge_has("bbb\\DATA"));
    handle=create_file_w_capture(settings,GENERIC_WRITE,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(write_file_capture(handle,data,4096,&amount,NULL));CloseHandle(handle);
    /* data currently contains B: deliberately replace settings with a career. */
    CHECK(bridge_has("ccc\\DATA"));
    CHECK(durable_receipts()==1);
    fixture(settings,0);
    handle=create_file_w_capture(b,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(read_file_capture(handle,data,4096,&amount,NULL));CloseHandle(handle);
    CHECK(bridge_has("bbb\\DATA"));
    CHECK(durable_receipts()==1); /* A verification read cannot consume a write. */
    handle=create_file_w_capture(settings,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(read_file_capture(handle,data,4096,&amount,NULL));CloseHandle(handle);
    handle=create_file_w_capture(settings,GENERIC_WRITE,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(write_file_capture(handle,data,4096,&amount,NULL));CloseHandle(handle);
    CHECK(bridge_has("bbb\\DATA"));
    /* Real FIFA loading pattern: seek past the independently read header. */
    handle=create_file_w_capture(a,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(SetFilePointer(handle,116,NULL,FILE_BEGIN)==116);
    CHECK(read_file_capture(handle,data,4096-116,&amount,NULL));CloseHandle(handle);
    CHECK(bridge_has("aaa\\DATA"));
    handle=create_file_w_capture(b,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(SetFilePointer(handle,116,NULL,FILE_BEGIN)==116);
    CHECK(read_file_capture(handle,data,1000,&amount,NULL));
    CHECK(bridge_has("aaa\\DATA"));
    CHECK(read_file_capture(handle,data,4096,&amount,NULL));CloseHandle(handle);
    CHECK(bridge_has("bbb\\DATA"));
    handle=create_file_w_capture(b,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(read_file_capture(handle,data,4096,&amount,NULL));CloseHandle(handle);
    CHECK(bridge_has("bbb\\DATA"));
    /* FIFA writes a fresh container in two pieces (116 + body). */
    handle=CreateFileW(b,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    CHECK(ReadFile(handle,data,4096,&amount,NULL));CloseHandle(handle);
    handle=create_file_w_capture(a,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,0,NULL);
    CHECK(write_file_capture(handle,data,116,&amount,NULL));
    CHECK(durable_receipts()==1);
    CHECK(bridge_has("bbb\\DATA"));
    CHECK(write_file_capture(handle,data+116,1000,&amount,NULL));
    CHECK(bridge_has("bbb\\DATA"));
    CHECK(write_file_capture(handle,data+1116,4096-1116,&amount,NULL));CloseHandle(handle);
    CHECK(bridge_has("aaa\\DATA"));
    CHECK(durable_receipts()==2); /* Only the completed chunked write is journaled. */
    puts("PASS: complete chunked career I/O only; previews/settings ignored; later load/write identity replaces earlier path");
    return 0;
}
