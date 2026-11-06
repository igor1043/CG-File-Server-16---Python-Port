/* RawEmail native ABI verified at InformJobOffer (5bcfaa0) and
 * EmailManager::AddRawEmail (5b569e0). All allocations and insertion run on
 * the real provider thread. Only our tagged messages use literal strings;
 * the three stock conversion calls otherwise retain their original path. */
#define BANK_MAIL_TAG "S16BANKMAIL:"
#include "career_mail_currency.inc"
typedef struct BankMailRequest {
    unsigned pid, club, due, epoch;
    uintptr_t context;
    char id[65], subject[256], body[4096];
} BankMailRequest;

static int bank_mail_string(const char *value, size_t capacity)
{
    size_t i;
    for (i=0; i<capacity; ++i) {
        if (!is_readable_range(value+i,1)) return 0;
        if (!value[i]) return 1;
    }
    return 0;
}

static void bank_mail_convert(void *manager, unsigned char *destination, unsigned char *raw)
{
    const char *subject = NULL, *body = NULL, *title;
    char localized_body[8192];
    typedef void (*Convert)(void *,void *,void *);
    typedef void (*SetText)(void *,void *,const char *);
    if (is_readable_range(raw,0x60)) {
        memcpy(&subject,raw+0x48,sizeof(subject));
        memcpy(&body,raw+0x58,sizeof(body));
    }
    if (subject && body && bank_mail_string(subject,384)
        && !strncmp(subject,BANK_MAIL_TAG,sizeof(BANK_MAIL_TAG)-1)
        && bank_mail_string(body,4096)
        && (title=subject+sizeof(BANK_MAIL_TAG)-1)
        && strspn(title,"0123456789abcdef")==64 && title[64]=='|') {
        SetText set = (SetText)(g_module_base+0x5c15210);
        set(destination,destination+0x18,title+65);
        if(strstr(body,"{{S16M:")){career_mail_currency(body,localized_body,sizeof(localized_body));body=localized_body;}
        set(destination,destination+0x20,body);
        return;
    }
    ((Convert)(g_module_base+0x5c12860))(manager,destination,raw);
}

static int bank_mail_unhex(const char *input, char *output, size_t capacity)
{
    size_t i,n=strcspn(input,"\r\n");
    if (!n || n%2 || n/2>=capacity) return 0;
    for (i=0;i<n;i+=2) {
        unsigned a,b;
        char x=input[i],y=input[i+1];
        if (!((x>='0'&&x<='9')||(x>='a'&&x<='f'))
            || !((y>='0'&&y<='9')||(y>='a'&&y<='f'))) return 0;
        a=x<='9'?(unsigned)(x-'0'):(unsigned)(x-'a'+10);
        b=y<='9'?(unsigned)(y-'0'):(unsigned)(y-'a'+10);
        output[i/2]=(char)((a<<4)|b);
        if (!output[i/2]) return 0;
    }
    output[n/2]=0;
    return 1;
}

static int bank_mail_read(const char *path, BankMailRequest *request)
{
    FILE *file=fopen(path,"rb");
    char line[8400]; int fields=0;
    memset(request,0,sizeof(*request));
    if (!file) return 0;
    while (fgets(line,sizeof(line),file)) {
        unsigned long long context;unsigned schema;
        if (sscanf(line,"schema=%u",&schema)==1) {if(schema==1)fields|=1;}
        else if (sscanf(line,"pid=%u",&request->pid)==1) fields|=2;
        else if (sscanf(line,"club=%u",&request->club)==1) fields|=4;
        else if (sscanf(line,"due=%u",&request->due)==1) fields|=8;
        else if (sscanf(line,"epoch=%u",&request->epoch)==1) fields|=256;
        else if (sscanf(line,"context=%llx",&context)==1) {request->context=(uintptr_t)context;fields|=16;}
        else if (!strncmp(line,"id=",3)) {
            size_t n=strcspn(line+3,"\r\n");
            if (n==64 && strspn(line+3,"0123456789abcdef")==64) {
                memcpy(request->id,line+3,64);request->id[64]=0;fields|=32;
            }
        } else if (!strncmp(line,"subject=",8) && bank_mail_unhex(line+8,request->subject,sizeof(request->subject))) fields|=64;
        else if (!strncmp(line,"body=",5) && bank_mail_unhex(line+5,request->body,sizeof(request->body))) fields|=128;
    }
    fclose(file);
    return fields==511;
}

static int bank_mail_exists(unsigned char *manager, const char *tag)
{
    unsigned slot;
    for (slot=0;slot<2;++slot) {
        uintptr_t at=*(uintptr_t *)(manager+0x50+slot*0x40);
        uintptr_t end=*(uintptr_t *)(manager+0x58+slot*0x40);
        if (at==end) continue;
        if (end<at || end-at>4096*8 || (end-at)%8 || !is_readable_range((void *)at,end-at)) return -1;
        for (;at<end;at+=8) {
            unsigned char *raw=*(unsigned char **)at;
            const char *subject;
            if (!is_readable_range(raw,0x60)) return -1;
            subject=*(const char **)(raw+0x48);
            if (subject && bank_mail_string(subject,384) && !strncmp(subject,tag,strlen(tag))) return 1;
        }
    }
    return 0;
}

static void *bank_mail_allocate(size_t size)
{
    void *allocator=((void *(*)(void))(g_module_base+0x44679b0))();
    typedef void *(*Allocate)(void *,size_t,const char *,int);
    if (!allocator) return NULL;
    return ((Allocate)(*(void ***)allocator)[2])(allocator,size,"Server16 bank mail",1);
}

static void bank_mail_free(void *value)
{
    void *allocator=((void *(*)(void))(g_module_base+0x44679b0))();
    if (value && allocator)
        ((void (*)(void *,void *,int))(*(void ***)allocator)[3])(allocator,value,0);
}

/* Resolve services through the verified career registry. A deferred Statistics
 * provider belongs to a particular hub view and is intentionally discarded
 * when entering Calendar/Loans; inbox delivery must not retain that owner. */
static unsigned char *bank_mail_service(uintptr_t registry, unsigned descriptor, size_t minimum)
{
    unsigned index; uintptr_t wrapper,service;
    if (!registry || memcmp(g_module_base+descriptor+7,"\xc7\x01",2)) return NULL;
    memcpy(&index,g_module_base+descriptor+9,sizeof(index));
    if (index>255 || !is_readable_range((void *)(registry+(uintptr_t)index*32+24),8)) return NULL;
    wrapper=*(uintptr_t *)(registry+(uintptr_t)index*32+24);
    if (!is_readable_range((void *)wrapper,8)) return NULL;
    service=*(uintptr_t *)wrapper;
    return is_readable_range((void *)service,minimum)?(unsigned char *)service:NULL;
}

static void bank_mail_status(const BankMailRequest *request,const char *status)
{
    char path[MAX_PATH],temporary[MAX_PATH]; FILE *file;
    snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\bank\\runtime\\native_mail_status.tsv",g_mod_dir);
    snprintf(temporary,sizeof(temporary),"%s.new",path);
    file=fopen(temporary,"wb");if(!file)return;
    fprintf(file,"schema=1\npid=%u\nclub=%u\nid=%s\nstatus=%s\n",request->pid,request->club,request->id,status);
    fclose(file);MoveFileExA(temporary,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
}

static void drain_bank_mail(void)
{
    static ULONGLONG next;
    BankMailRequest request;
    char path[MAX_PATH],receipt[MAX_PATH],temporary[MAX_PATH],tag[96],subject[384];
    unsigned char *mail,*calendar,*raw,*value,*read_value,*notify_value;
    CareerContextRead captured;
    uintptr_t service,context,registry;
    int selected,today,exists,parts[3];
    FILE *file;
    typedef void (*SetString)(void *,void *,const char *);
    SetString set=(SetString)(g_module_base+0x5c152c0);
    memcpy(&captured,&Fifa16CareerContextRead,sizeof(captured));
    service=captured.service;registry=captured.registry;
    if (g_current_stats_provider_owner || !fce_runtime_is_stable()
        || captured.schema!=1 || captured.size!=sizeof(captured) || captured.sequence&1
        || captured.pid!=GetCurrentProcessId() || captured.owner_thread!=GetCurrentThreadId()
        || captured.epoch!=fce_runtime_context_epoch() || GetTickCount64()<next
        || !is_readable_range((void *)service,32)
        || *(uintptr_t *)service!=captured.vtable) return;
    next=GetTickCount64()+200;
    snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\bank\\runtime\\native_mail_request.tsv",g_mod_dir);
    if (!bank_mail_read(path,&request) || request.pid!=GetCurrentProcessId()
        || !fce_date_valid((int)request.due)
        || request.epoch!=fce_runtime_context_epoch()
        || request.epoch!=captured.epoch) return;
    bank_mail_status(&request,"checking_context");
    selected=*(int *)(service+0x14);
    if (selected<0 || selected>7) return;
    context=*(uintptr_t *)(service+0x18)+(uintptr_t)selected*0x318;
    if (context!=request.context || !is_readable_range((void *)context,0x318)
        || *(unsigned *)(context+0x1a4)!=request.club || *(int *)(context+0x18c)!=1) return;
    calendar=bank_mail_service(registry,0x44563f0,0x40);
    if (!calendar) {bank_mail_status(&request,"waiting_calendar");return;}
    memcpy(parts,calendar+0x34,sizeof(parts));today=fce_date_pack(parts[0],parts[1],parts[2]);
    if (!fce_date_valid(today) || today<(int)request.due) {bank_mail_status(&request,"waiting_due_date");return;}
    mail=bank_mail_service(registry,0x44565f0,0x170);
    if (!mail || *(uintptr_t *)(mail+8)!=registry || *(int *)(mail+0x168)!=0
        || Fifa16CareerContextRead.sequence!=captured.sequence) {bank_mail_status(&request,"waiting_inbox");return;}
    snprintf(tag,sizeof(tag),BANK_MAIL_TAG "%s|",request.id);
    exists=bank_mail_exists(mail,tag);
    if (exists<0) return;
    if (!exists) {
        static const unsigned char ctor[]={0x48,0x89,0x5c,0x24,0x08};
        if (memcmp(g_module_base+0x5b4af80,ctor,sizeof(ctor))
            || memcmp(g_module_base+0x5b569e0,"\x48\x89\x7c\x24\x20",5)) return;
        raw=(unsigned char *)bank_mail_allocate(0xf0);
        value=(unsigned char *)bank_mail_allocate(24);
        read_value=(unsigned char *)bank_mail_allocate(16);
        notify_value=(unsigned char *)bank_mail_allocate(16);
        if (!raw || !value || !read_value || !notify_value) {
            bank_mail_free(raw);bank_mail_free(value);bank_mail_free(read_value);bank_mail_free(notify_value);return;
        }
        memset(raw,0,0xf0);
        ((void *(*)(void *))(g_module_base+0x5b4af80))(raw);
        *(int *)(raw+0)=1; *(int *)(raw+4)=1; *(unsigned *)(raw+8)=request.club;
        *(int *)(raw+0x18)=1;
        memset(value,0,24);*(uintptr_t *)value=(uintptr_t)g_module_base+0x3031850;
        *(unsigned *)(value+8)=request.club;*(int *)(value+0x10)=1;
        *(void **)(raw+0x10)=value;
        memset(read_value,0,16);*(uintptr_t *)read_value=(uintptr_t)g_module_base+0x30317f0;
        memset(notify_value,0,16);*(uintptr_t *)notify_value=(uintptr_t)g_module_base+0x30317f0;
        *(int *)(notify_value+8)=1;
        *(void **)(raw+0x20)=read_value;*(void **)(raw+0x28)=notify_value;
        snprintf(subject,sizeof(subject),"%s%s",tag,request.subject);
        set(raw,raw+0x48,subject);set(raw,raw+0x58,request.body);
        /* Crossing several calendar days must not redate the original event.
         * The receipt below separately records the actual insertion day. */
        *(int *)(raw+0x90)=(int)request.due;*(int *)(raw+0x94)=(int)request.due;
        raw[0x9a]=1;raw[0x9b]=1;
        *(int *)(raw+0x9c)=1;*(unsigned *)(raw+0xa0)=request.club;
        ((void (*)(void *,int,void *))(g_module_base+0x5b569e0))(mail,selected,raw);
        if (bank_mail_exists(mail,tag)!=1) return;
        append_loader_log("career_bank_mail_delivered");
    }
    snprintf(receipt,sizeof(receipt),"%s\\runtime\\club_environment\\bank\\runtime\\native_mail_receipt.tsv",g_mod_dir);
    snprintf(temporary,sizeof(temporary),"%s.new",receipt);
    file=fopen(temporary,"wb");
    if (!file) return;
    fprintf(file,"schema=1\npid=%u\nclub=%u\ncontext=%llx\nepoch=%u\nid=%s\ndate=%d\n",request.pid,request.club,(unsigned long long)request.context,request.epoch,request.id,today);
    fclose(file);
    MoveFileExA(temporary,receipt,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
    bank_mail_status(&request,"delivered");
}
