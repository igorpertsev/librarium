class PublishersController < ApplicationController
  def index
    @publishers = Publisher.all
  end

  def show
    @publisher = Publisher.find(params[:id])
  end

  def new
    @publisher = Publisher.new
  end

  def create
    @publisher = Publisher.new(publisher_params)
    if @publisher.save
      respond_to do |format|
        format.html { redirect_to publishers_path }
        format.turbo_stream
      end
    else
      render :new
    end
  end

  def edit
    @publisher = Publisher.find(params[:id])
  end

  def update
    @publisher = Publisher.find(params[:id])
    if @publisher.update(publisher_params)
      respond_to do |format|
        format.html { redirect_to @publisher }
        format.turbo_stream
      end
    else
      render :edit
    end
  end

  def destroy
    @publisher = Publisher.find(params[:id])
    @publisher.destroy
    respond_to do |format|
      format.html { redirect_to genres_path }
      format.turbo_stream
    end
  end

  private

  def publisher_params
    params.require(:publisher).permit(:name)
  end
end
