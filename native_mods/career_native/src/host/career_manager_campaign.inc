/* Immutable, date-scoped competition evidence for the coach calendar.
 * Reads the existing FCE cache, never a UI provider and never the saved DATA. */
static unsigned long manager_campaign_generation,manager_campaign_derived;
static int manager_campaign_date;
static unsigned manager_campaign_epoch;
static uintptr_t manager_campaign_context;
static void manager_archive_campaign(const PreparedViewRecord *request)
{
    FceLiveSnapshot *snapshot=fce_runtime_calendar_acquire();const FceModel *model;
    unsigned long revision,derived;size_t i,count=0;FceDerivedStanding *rows=NULL;
    char folder[MAX_PATH],path[MAX_PATH],temporary[MAX_PATH];FILE *file=NULL;int ok=1;
    CareerContextRead checked;
    if(!snapshot)return;
    model=fce_runtime_model(snapshot);revision=fce_runtime_generation(snapshot);derived=fce_runtime_derived_revision();
    if(!model || model->date!=request->date)goto done;
    if(manager_campaign_generation==revision && manager_campaign_derived==derived && manager_campaign_date==request->date
        && manager_campaign_epoch==request->epoch && manager_campaign_context==(uintptr_t)request->context)goto done;
    if(model->node_count>65536 || model->standing_count>65536 || model->fixture_count>65536 || !prepared_view_scope(request,&checked))goto done;
    if(snprintf(folder,sizeof(folder),"%s\\runtime\\manager_market\\league_days",g_mod_dir)>=(int)sizeof(folder))goto done;
    if(!CreateDirectoryA(folder,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)goto done;
    if(snprintf(folder,sizeof(folder),"%s\\runtime\\manager_market\\league_days\\%lu-%llu-%u-%llx",g_mod_dir,
        GetCurrentProcessId(),request->created,request->epoch,request->context)>=(int)sizeof(folder))goto done;
    if(!CreateDirectoryA(folder,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)goto done;
    if(snprintf(path,sizeof(path),"%s\\%d.campaign.json",folder,request->date)>=(int)sizeof(path))goto done;
    if(snprintf(temporary,sizeof(temporary),"%s.new",path)>=(int)sizeof(temporary))goto done;
    file=fopen(temporary,"wb");if(!file)goto done;
    if(fprintf(file,"{\"schema\":1,\"complete\":1,\"pid\":%lu,\"created\":%llu,\"epoch\":%u,\"context\":%llu,\"registry\":%llu,\"club\":%u,\"date\":%d,\"nodes\":[",
        GetCurrentProcessId(),request->created,request->epoch,request->context,request->registry,request->club,request->date)<0)ok=0;
    for(i=0;ok && i<model->node_count;++i){const FceCompNode *n=model->nodes+i;
        if(fprintf(file,"%s[%d,%d,%d,%d,%d]",i?",":"",n->id,n->parent,n->type,n->asset,n->stage_kind)<0)ok=0;}
    if(fputs("],\"standings\":[",file)==EOF)ok=0;
    for(i=0;ok && i<model->standing_count;++i){const FceStanding *s=model->standings+i;
        if(fprintf(file,"%s[%d,%d,%d,%u,%u,%u,%u,%u,%u,%u]",i?",":"",s->standing_id,s->competition_object,s->team,s->home_wins,s->home_draws,s->home_losses,s->away_wins,s->away_draws,s->away_losses,s->played)<0)ok=0;}
    if(fputs("],\"derivedStandings\":[",file)==EOF)ok=0;
    count=fce_runtime_derived_copy(NULL,0,model->date);rows=count?calloc(count,sizeof(*rows)):NULL;
    if(count && !rows)ok=0;
    if(rows){count=fce_runtime_derived_copy(rows,count,model->date);
        for(i=0;ok && i<count;++i){const FceDerivedStanding *d=rows+i;const FceStanding *s=&d->standing;
            if(fprintf(file,"%s[%d,%d,%d,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u]",i?",":"",s->standing_id,s->competition_object,s->team,s->home_wins,s->home_draws,s->home_losses,s->away_wins,s->away_draws,s->away_losses,s->played,d->home_gf,d->home_ga,d->away_gf,d->away_ga)<0)ok=0;}}
    if(fputs("],\"fixtures\":[",file)==EOF)ok=0;
    for(i=0;ok && i<model->fixture_count;++i){const FceFixture *f=model->fixtures+i;
        if(fprintf(file,"%s[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]",i?",":"",f->id,f->competition_object,f->stage,f->date_raw,f->time_raw,f->home,f->away,f->home_score,f->away_score,f->played_raw,f->round)<0)ok=0;}
    if(fputs("]}",file)==EOF)ok=0;if(fclose(file))ok=0;file=NULL;
    if(!prepared_view_scope(request,&checked))ok=0;
    if(ok && MoveFileExA(temporary,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)){
        manager_campaign_generation=revision;manager_campaign_derived=derived;manager_campaign_date=request->date;
        manager_campaign_epoch=request->epoch;manager_campaign_context=(uintptr_t)request->context;
    }else DeleteFileA(temporary);
done:
    free(rows);if(file)fclose(file);fce_runtime_release(snapshot);
}
